"""Precompute Phase 13 grid-cell metrics in PostGIS (table analytics_grid_cells).

One row per grid cell that has occurrence records. Every component is stored separately so the
API can rank or filter on any of them; no weighted composite score is calculated.

Protected-area coverage is the share of the cell's area inside each layer (area-based, so it is
not affected by obscured point coordinates).

Usage: python scripts/phase13_build_grid_metrics.py
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data" / "analytics" / "grid_metrics_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
GRID_SIZE_DEGREES = 0.75  # matches backend/app/services/concentration.py
RECENT_YEARS = 10
THREATENED_CATEGORIES = ["CR", "EN", "VU"]
COVERAGE_CLASSES = ("wildlife_pa", "tiger_reserve", "forest", "other_designation")

BUILD_SQL = """
WITH occ AS (
    SELECT o.species_id, o.year, o.state, o.dataset_key, o.coordinate_uncertainty_class,
           floor(o.longitude / %(grid)s) * %(grid)s AS lon_min,
           floor(o.latitude / %(grid)s) * %(grid)s AS lat_min,
           COALESCE(verified.iucn_category, s.current_iucn_status) AS category,
           verified.iucn_category IS NOT NULL AS category_verified
    FROM occurrences AS o
    JOIN species AS s ON s.species_id = o.species_id
    LEFT JOIN LATERAL (
        SELECT ca.iucn_category FROM conservation_assessments AS ca
        WHERE ca.species_id = o.species_id ORDER BY ca.assessment_year DESC LIMIT 1
    ) AS verified ON TRUE
), cells AS (
    SELECT lon_min, lat_min,
           COUNT(*) AS record_count,
           COUNT(*) FILTER (WHERE coordinate_uncertainty_class IN ('precise', 'moderate')) AS records_within_10_km,
           COUNT(DISTINCT species_id) AS observed_species,
           COUNT(DISTINCT species_id) FILTER (WHERE coordinate_uncertainty_class IN ('precise', 'moderate')) AS observed_species_within_10_km,
           ARRAY_AGG(DISTINCT species_id ORDER BY species_id) AS species_ids,
           COUNT(DISTINCT species_id) FILTER (WHERE category = ANY(%(threatened)s)) AS threatened_species,
           COALESCE(ARRAY_AGG(DISTINCT species_id ORDER BY species_id) FILTER (WHERE category = ANY(%(threatened)s)), '{}') AS threatened_species_ids,
           BOOL_AND(category_verified) AS threatened_status_verified,
           COUNT(DISTINCT year) AS years_with_records,
           MIN(year) AS first_year, MAX(year) AS last_year,
           COUNT(*) FILTER (WHERE year > %(recent_from)s) AS recent_records,
           COUNT(DISTINCT dataset_key) AS dataset_count,
           MODE() WITHIN GROUP (ORDER BY state) AS dominant_state
    FROM occ GROUP BY lon_min, lat_min
)
INSERT INTO analytics_grid_cells (
    cell_id, grid_size_degrees, geom, dominant_state, record_count, records_within_10_km, observed_species,
    observed_species_within_10_km, species_ids, threatened_species, threatened_species_ids, threatened_status_verified,
    years_with_records, first_year, last_year, recent_records, dataset_count,
    wildlife_pa_pct, tiger_reserve_pct, forest_pct, other_designation_pct)
SELECT format('%%s_%%s', lon_min, lat_min), %(grid)s,
       ST_MakeEnvelope(lon_min, lat_min, lon_min + %(grid)s, lat_min + %(grid)s, 4326),
       dominant_state, record_count, records_within_10_km, observed_species, observed_species_within_10_km,
       species_ids, threatened_species, threatened_species_ids, threatened_status_verified,
       years_with_records, first_year, last_year, recent_records, dataset_count,
       0, 0, 0, 0
FROM cells
"""

COVERAGE_SQL = """
UPDATE analytics_grid_cells AS cell SET {column} = COALESCE((
    SELECT ROUND((100 * ST_Area(ST_Intersection(cell.geom, ST_MakeValid(ST_Union(pa.geom)))::geography)
                  / ST_Area(cell.geom::geography))::numeric, 2)::float
    FROM protected_areas AS pa
    WHERE pa.pa_class = %(pa_class)s AND ST_Intersects(pa.geom, cell.geom)
), 0)
"""


def main() -> None:
    started = time.monotonic()
    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM analytics_grid_cells")
            cursor.execute(BUILD_SQL, {
                "grid": GRID_SIZE_DEGREES,
                "threatened": THREATENED_CATEGORIES,
                "recent_from": date.today().year - 1 - RECENT_YEARS,
            })
            cells = cursor.rowcount
            for pa_class in COVERAGE_CLASSES:
                cursor.execute(COVERAGE_SQL.format(column=f"{pa_class}_pct"), {"pa_class": pa_class})
                print(f"  {pa_class} coverage computed ({time.monotonic() - started:.0f}s)", flush=True)
            cursor.execute(
                "SELECT COUNT(*) FILTER (WHERE threatened_species > 0), BOOL_AND(threatened_status_verified), "
                "ROUND(AVG(wildlife_pa_pct)::numeric, 1)::float FROM analytics_grid_cells"
            )
            with_threatened, verified, mean_wildlife = cursor.fetchone()
            cursor.execute("SELECT ARRAY_AGG(DISTINCT source_version ORDER BY source_version) FROM protected_areas")
            source_versions = cursor.fetchone()[0]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "grid_size_degrees": GRID_SIZE_DEGREES,
        "cells": cells,
        "cells_with_threatened_species": with_threatened,
        "threatened_categories": THREATENED_CATEGORIES,
        "threatened_status_verified": bool(verified),
        "recent_records_window": f"last {RECENT_YEARS} complete years",
        "mean_wildlife_pa_pct": mean_wildlife,
        "protected_area_source_versions": source_versions,
        "seconds": round(time.monotonic() - started, 1),
        "notes": [
            "Threatened species use verified IUCN categories where imported, otherwise the project's source-reported list.",
            "Coverage percentages are area shares of each cell and do not depend on point precision.",
            "Species counts are observed in the loaded records only; they are not sampling-corrected richness.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
