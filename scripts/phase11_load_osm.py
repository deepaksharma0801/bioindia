"""Idempotently load the OpenStreetMap wildlife protected-area and tiger-reserve layers into PostGIS.

The main wildlife layer is OSM National Parks, Wildlife Sanctuaries, and Conservation and
Community Reserves. Tiger reserves include buffer zones, so they load as a separate class.
Forest and other designations come from WDPA instead (phase11_load_wdpa.py).

Input: data/processed/osm_protected_areas.gpkg (from phase11_compare_osm_wdpa.py)

Usage:
    python scripts/phase11_load_osm.py --dry-run   # report what would load
    python scripts/phase11_load_osm.py             # load into PostGIS (DATABASE_URL)
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OSM_LAYER = ROOT / "data" / "processed" / "osm_protected_areas.gpkg"
PBF = ROOT / "data" / "raw" / "protected_areas" / "osm" / "india-latest.osm.pbf"
SCHEMA = ROOT / "backend" / "app" / "database" / "schema.sql"
REPORT = ROOT / "data" / "analytics" / "osm_protected_area_load_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

SOURCE = "OpenStreetMap contributors (ODbL 1.0), Geofabrik india-latest.osm.pbf"
PA_CLASS_BY_OSM_CLASS = {
    "national_park": "wildlife_pa",
    "wildlife_sanctuary": "wildlife_pa",
    "conservation_community_reserve": "wildlife_pa",
    "tiger_reserve": "tiger_reserve",
}
DUAL_DESIGNATION = "National Park or Wildlife Sanctuary within a Tiger Reserve (shared OSM outline)"
DESIGNATION_BY_OSM_CLASS = {
    "national_park": "National Park",
    "wildlife_sanctuary": "Wildlife Sanctuary",
    "conservation_community_reserve": "Conservation or Community Reserve",
    "tiger_reserve": "Tiger Reserve",
}


def source_version() -> str:
    extract_date = datetime.fromtimestamp(PBF.stat().st_mtime, tz=timezone.utc).date().isoformat()
    return f"OSM_geofabrik_india_{extract_date}"


def build_rows(records) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """One row per feature and layer; a dual-named tiger reserve also gets a wildlife_pa row."""
    rows, dual = [], []
    for record in records:
        name = record.name if isinstance(record.name, str) else f"Unnamed OSM {record.osm_id}"
        base = {"name": name, "geometry": record.geometry.wkb}
        rows.append({
            **base,
            "protected_area_id": f"OSM:{record.osm_id}",
            "designation": DESIGNATION_BY_OSM_CLASS[record.osm_class],
            "pa_class": PA_CLASS_BY_OSM_CLASS[record.osm_class],
        })
        if record.osm_class == "tiger_reserve" and record.also_wildlife_pa:
            rows.append({
                **base,
                "protected_area_id": f"OSM:{record.osm_id}#wildlife_pa",
                "designation": DUAL_DESIGNATION,
                "pa_class": "wildlife_pa",
            })
            dual.append({"osm_id": record.osm_id, "name": name, "basis": record.dual_basis})
    return rows, dual


def load_rows():
    import geopandas as gpd

    layer = gpd.read_file(OSM_LAYER)
    selected = layer[layer["osm_class"].isin(PA_CLASS_BY_OSM_CLASS)]
    rows, dual = build_rows(selected.itertuples(index=False))
    return rows, dual, Counter(selected["osm_class"]), len(layer) - len(selected)


def load_postgis(rows: list[dict[str, object]], version: str) -> None:
    import psycopg

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA.read_text(encoding="utf-8"))
            # Replace the whole OSM layer so features removed from OSM do not linger.
            cursor.execute("DELETE FROM protected_areas WHERE protected_area_id LIKE 'OSM:%%'")
            cursor.executemany(
                """INSERT INTO protected_areas
                (protected_area_id, name, designation, pa_class, source, source_version, geom)
                VALUES (%(protected_area_id)s, %(name)s, %(designation)s, %(pa_class)s, %(source)s, %(source_version)s,
                        ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%(geometry)s), 4326)), 3)))""",
                [{**row, "source": SOURCE, "source_version": version} for row in rows],
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would load without touching PostGIS.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, dual, by_osm_class, not_loaded = load_rows()
    version = source_version()
    if not args.dry_run:
        load_postgis(rows, version)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE,
        "source_version": version,
        "dry_run": args.dry_run,
        "records_selected": len(rows),
        "by_osm_class": dict(by_osm_class),
        "by_pa_class": dict(Counter(row["pa_class"] for row in rows)),
        "tiger_reserves_also_loaded_as_wildlife_pa": sorted(dual, key=lambda item: item["name"]),
        "dual_classification_rule": "tiger_reserve features whose name also says National Park or WLS/Sanctuary, or that are on the documented manual list in phase11_compare_osm_wdpa.py, get a second row (id suffix '#wildlife_pa') in the wildlife layer; their outline may include buffer zones",
        "osm_features_not_loaded": not_loaded,
        "not_loaded_reason": "forest and other OSM classes are not loaded; WDPA supplies those layers. Excluded zones and proposed sites are never loaded.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
