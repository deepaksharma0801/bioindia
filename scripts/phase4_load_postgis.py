"""Load screened occurrences into PostGIS, applying the spatial quality rules and duplicate removal in SQL.

Steps (all idempotent; the GBIF occurrence set is replaced as a whole):
  1. Load reference layers: Indian states (geoBoundaries) and mapped zoos (OSM), subdivided for fast lookups.
  2. Upsert the species master.
  3. COPY data/processed/occurrences_screened.csv into a staging table.
  4. Exclude records inside a mapped zoo, and records not within 10 km of an Indian state; attribute the
     containing (or nearest, for coastal points) state.
  5. Exclude repeat uploads (same species, named observer, ~11 m location, exact day); flag separate
     sightings that share place and date.
  6. Replace the GBIF rows in `occurrences`, append SQL exclusions to the exclusion log, write a report.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
SCREENED = PROCESSED / "occurrences_screened.csv"
STATES = ROOT / "data" / "raw" / "india_states_admin_current.geojson"
ZOOS = ROOT / "data" / "raw" / "protected_areas" / "osm" / "osm_zoos.gpkg"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
COASTAL_TOLERANCE_M = 10_000

SPECIES_COLUMNS = [
    "species_id", "scientific_name", "canonical_name", "common_name", "kingdom", "phylum", "class_name",
    "order_name", "family", "genus", "species_epithet", "gbif_taxon_key", "iucn_taxon_id", "native_status",
    "endemic_status", "environment_type", "current_iucn_status", "current_iucn_status_source", "source",
    "source_dataset_identifier", "license",
]
STAGING_COLUMNS = [
    "occurrence_id", "species_id", "scientific_name_original", "latitude", "longitude", "coordinate_uncertainty",
    "coordinate_uncertainty_class", "event_date", "date_precision", "year", "month", "basis_of_record", "dataset_key",
    "source", "source_record_id", "license", "quality_flags", "gbif_issues", "source_download_doi", "recorded_by",
]

STAGING_SQL = """
DROP TABLE IF EXISTS occurrences_staging;
CREATE UNLOGGED TABLE occurrences_staging (
    occurrence_id TEXT, species_id TEXT, scientific_name_original TEXT, latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION, coordinate_uncertainty DOUBLE PRECISION, coordinate_uncertainty_class TEXT,
    event_date DATE, date_precision TEXT, year SMALLINT, month SMALLINT, basis_of_record TEXT, dataset_key TEXT,
    source TEXT, source_record_id TEXT, license TEXT, quality_flags TEXT[], gbif_issues TEXT[],
    source_download_doi TEXT, recorded_by TEXT,
    geom geometry(Point, 4326), state TEXT, exclusion_reason TEXT
);
"""

SPATIAL_SQL = [
    ("geometry", "UPDATE occurrences_staging SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)"),
    ("index", "CREATE INDEX occurrences_staging_geom_gix ON occurrences_staging USING GIST (geom); ANALYZE occurrences_staging"),
    # Free-flying birds inside zoo grounds are wild, so birds are exempt from the zoo rule.
    ("zoos", """UPDATE occurrences_staging AS o SET exclusion_reason = 'inside_mapped_zoo'
                FROM species AS s
                WHERE s.species_id = o.species_id AND COALESCE(s.class_name, '') <> 'Aves'
                  AND EXISTS (SELECT 1 FROM reference_zoos AS z WHERE ST_Intersects(z.geom, o.geom))"""),
    ("states", """UPDATE occurrences_staging AS o SET state = s.state
                  FROM reference_states_sub AS s
                  WHERE o.exclusion_reason IS NULL AND ST_Intersects(s.geom, o.geom)"""),
    ("coastal", f"""UPDATE occurrences_staging AS o SET state = (
                       SELECT s.state FROM reference_states_sub AS s
                       WHERE ST_DWithin(s.geom::geography, o.geom::geography, {COASTAL_TOLERANCE_M})
                       ORDER BY ST_Distance(s.geom::geography, o.geom::geography) LIMIT 1)
                   WHERE o.exclusion_reason IS NULL AND o.state IS NULL
                     AND ST_DWithin(o.geom, (SELECT ST_Collect(geom) FROM reference_states), 0.2)"""),
    ("outside_india", "UPDATE occurrences_staging SET exclusion_reason = 'coordinate_outside_india' WHERE exclusion_reason IS NULL AND state IS NULL"),
    ("duplicates", """WITH ranked AS (
                         SELECT occurrence_id,
                                FIRST_VALUE(source_record_id) OVER w AS keeper,
                                ROW_NUMBER() OVER w AS position
                         FROM occurrences_staging
                         WHERE exclusion_reason IS NULL AND date_precision = 'day' AND recorded_by <> ''
                         WINDOW w AS (PARTITION BY species_id, ROUND(latitude::numeric, 4), ROUND(longitude::numeric, 4),
                                                   event_date, LOWER(recorded_by)
                                      ORDER BY coordinate_uncertainty NULLS LAST, source_record_id::bigint))
                     UPDATE occurrences_staging AS o SET exclusion_reason = 'duplicate_of_gbif_' || r.keeper
                     FROM ranked AS r WHERE r.occurrence_id = o.occurrence_id AND r.position > 1"""),
    ("shared_place_date", """WITH shared AS (
                                SELECT species_id, ROUND(latitude::numeric, 4) AS lat, ROUND(longitude::numeric, 4) AS lon,
                                       event_date, date_precision
                                FROM occurrences_staging WHERE exclusion_reason IS NULL
                                GROUP BY 1, 2, 3, 4, 5 HAVING COUNT(*) > 1)
                            UPDATE occurrences_staging AS o SET quality_flags = o.quality_flags || 'shared_place_and_date'::text
                            FROM shared AS s
                            WHERE o.exclusion_reason IS NULL AND o.species_id = s.species_id
                              AND ROUND(o.latitude::numeric, 4) = s.lat AND ROUND(o.longitude::numeric, 4) = s.lon
                              AND o.event_date = s.event_date AND o.date_precision = s.date_precision"""),
]

REPLACE_SQL = """
DELETE FROM occurrence_land_pressure WHERE occurrence_id IN (SELECT occurrence_id FROM occurrences WHERE source = 'GBIF');
DELETE FROM occurrences WHERE source = 'GBIF';
INSERT INTO occurrences (occurrence_id, species_id, scientific_name_original, geom, latitude, longitude,
    coordinate_uncertainty, coordinate_uncertainty_class, event_date, date_precision, year, month, state,
    basis_of_record, dataset_key, source, source_record_id, license, quality_flags, gbif_issues, source_download_doi)
SELECT occurrence_id, species_id, scientific_name_original, geom, latitude, longitude,
    coordinate_uncertainty, coordinate_uncertainty_class, event_date, date_precision, year, month, state,
    basis_of_record, dataset_key, source, source_record_id, license, quality_flags, gbif_issues, source_download_doi
FROM occurrences_staging WHERE exclusion_reason IS NULL;
"""


def load_reference_layers(cursor) -> None:
    import geopandas as gpd

    states = gpd.read_file(STATES).to_crs("EPSG:4326")
    zoos = gpd.read_file(ZOOS).to_crs("EPSG:4326")
    cursor.execute("""
        DROP TABLE IF EXISTS reference_states, reference_states_sub, reference_zoos;
        CREATE TABLE reference_states (state TEXT PRIMARY KEY, geom geometry(MultiPolygon, 4326));
        CREATE TABLE reference_zoos (osm_id TEXT, name TEXT, geom geometry(Geometry, 4326));
    """)
    cursor.executemany(
        "INSERT INTO reference_states VALUES (%s, ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%s), 4326))))",
        [(row.state, row.geometry.wkb) for row in states.itertuples()],
    )
    cursor.executemany(
        "INSERT INTO reference_zoos VALUES (%s, %s, ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%s), 4326)))",
        [(str(row.osm_id), row.name, row.geometry.wkb) for row in zoos.itertuples() if row.geometry is not None],
    )
    cursor.execute("""
        CREATE TABLE reference_states_sub AS SELECT state, ST_Subdivide(geom, 256) AS geom FROM reference_states;
        CREATE INDEX ON reference_states_sub USING GIST (geom);
        CREATE INDEX ON reference_zoos USING GIST (geom);
        ANALYZE reference_states_sub; ANALYZE reference_zoos;
    """)


def main() -> None:
    started = time.monotonic()
    species = json.loads((PROCESSED / "species_master.json").read_text(encoding="utf-8"))

    def step(label: str) -> None:
        print(f"  {label} ({time.monotonic() - started:.0f}s)", flush=True)

    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            load_reference_layers(cursor)
            step("reference layers loaded")
            names = ", ".join(SPECIES_COLUMNS)
            values = ", ".join(f"%({column})s" for column in SPECIES_COLUMNS)
            updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in SPECIES_COLUMNS if column != "species_id")
            cursor.executemany(f"INSERT INTO species ({names}) VALUES ({values}) ON CONFLICT (species_id) DO UPDATE SET {updates}", species)
            cursor.execute(STAGING_SQL)
            with SCREENED.open("rb") as handle, cursor.copy(f"COPY occurrences_staging ({', '.join(STAGING_COLUMNS)}) FROM STDIN WITH (FORMAT csv)") as copy:
                while chunk := handle.read(1 << 20):
                    copy.write(chunk)
            step("screened records copied")
            for label, sql in SPATIAL_SQL:
                cursor.execute(sql)
                step(label)
            cursor.execute(REPLACE_SQL)
            step("occurrences replaced")
            cursor.execute(
                "SELECT source_record_id, species_id, exclusion_reason FROM occurrences_staging WHERE exclusion_reason IS NOT NULL"
            )
            sql_exclusions = cursor.fetchall()
            cursor.execute("SELECT COUNT(*), COUNT(DISTINCT species_id) FROM occurrences WHERE source = 'GBIF'")
            loaded, species_loaded = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM occurrences_staging")
            staged = cursor.fetchone()[0]
            cursor.execute("DROP TABLE occurrences_staging")

    with (ANALYTICS / "occurrence_exclusions.csv").open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerows(sql_exclusions)
    reasons: dict[str, int] = {}
    for _, _, reason in sql_exclusions:
        key = "duplicate_record" if reason.startswith("duplicate_of_") else reason
        reasons[key] = reasons.get(key, 0) + 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "species_upserted": len(species),
        "records_staged": staged,
        "excluded_in_postgis": len(sql_exclusions),
        "exclusions_by_reason": reasons,
        "records_loaded": loaded,
        "species_with_records": species_loaded,
        "rules": {
            "inside_mapped_zoo": "point intersects an OSM zoo outline (point-only zoos buffered 500 m); birds exempt",
            "coordinate_outside_india": f"not within {COASTAL_TOLERANCE_M} m of a geoBoundaries IND ADM1 state",
            "state": "containing state, else nearest state within the coastal tolerance",
            "duplicate_record": "same species, named observer, coordinates rounded to 4 decimals (~11 m) and exact day; smallest stated uncertainty kept",
            "shared_place_and_date": "flag on kept records sharing species, rounded coordinates and date",
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    (ANALYTICS / "load_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
