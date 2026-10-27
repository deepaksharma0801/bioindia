"""Classify the WDPA India download and idempotently load its forest and other-designation layers into PostGIS.

The public WDPA release lacks most Indian National Park and Wildlife Sanctuary boundaries
(see data/analytics/osm_wdpa_protected_area_comparison.json), so the main wildlife layer
comes from OpenStreetMap (phase11_load_osm.py). From WDPA only legal forest categories and
other designations are loaded; its wildlife records are still classified and written to
data/processed/wdpa_wildlife_protected_areas.gpkg for the coverage comparison.

Usage:
    python scripts/phase11_load_wdpa.py --dry-run   # classify and write reports only
    python scripts/phase11_load_wdpa.py             # also load into PostGIS (DATABASE_URL)
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
WDPA_DIR = ROOT / "data" / "raw" / "protected_areas" / "extracted"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
WILDLIFE_OUTPUT = PROCESSED / "wdpa_wildlife_protected_areas.gpkg"
REPORT = ANALYTICS / "protected_area_classification_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

SOURCE_VERSION = "WDPA_WDOECM_Oct2026_Public_IND"
SOURCE = "UNEP-WCMC and IUCN (2026), Protected Planet: WDPA and WD-OECM, October 2026"
ATTRIBUTE_COLUMNS = [
    "SITE_ID", "SITE_PID", "NAME_ENG", "DESIG_ENG", "DESIG_TYPE",
    "STATUS", "STATUS_YR", "REALM", "REP_AREA", "GIS_AREA",
]
BATCH_SIZE = 1000

WILDLIFE_PA = "wildlife_pa"
FOREST = "forest"
OTHER = "other_designation"
PROPOSED = "proposed"
LOADED_CLASSES = (FOREST, OTHER)


def classify(designation: str | None, status: str | None) -> str:
    """Return the protected-area class for one WDPA record."""
    if (status or "").strip().casefold() == "proposed":
        return PROPOSED
    text = (designation or "").strip().casefold()
    if text == "national park" or text == "sanctuary" or "wildlife sanctuary" in text:
        return WILDLIFE_PA
    if text in {"conservation reserve", "community reserve"}:
        return WILDLIFE_PA
    if "forest" in text:
        return FOREST
    return OTHER


def polygon_layers() -> list[Path]:
    paths = sorted(WDPA_DIR.glob("part_*/*-polygons.shp"))
    if not paths:
        raise SystemExit(f"No WDPA polygon shapefiles found under {WDPA_DIR}")
    return paths


def point_record_count() -> int:
    import pyogrio

    return sum(pyogrio.read_info(path)["features"] for path in sorted(WDPA_DIR.glob("part_*/*-points.shp")))


def read_attributes():
    import pandas as pd
    import pyogrio

    frames = [pyogrio.read_dataframe(path, columns=ATTRIBUTE_COLUMNS, read_geometry=False) for path in polygon_layers()]
    attributes = pd.concat(frames, ignore_index=True)
    attributes["pa_class"] = [classify(d, s) for d, s in zip(attributes["DESIG_ENG"], attributes["STATUS"])]
    return attributes


def write_wildlife_layer() -> int:
    import geopandas as gpd
    import pandas as pd
    import pyogrio

    frames = []
    for path in polygon_layers():
        frame = pyogrio.read_dataframe(path, columns=ATTRIBUTE_COLUMNS)
        frame["pa_class"] = [classify(d, s) for d, s in zip(frame["DESIG_ENG"], frame["STATUS"])]
        frames.append(frame[frame["pa_class"] == WILDLIFE_PA])
    wildlife = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    wildlife.to_file(WILDLIFE_OUTPUT, driver="GPKG", layer="wildlife_protected_areas")
    return len(wildlife)


def build_report(attributes, points: int, wildlife_written: int) -> dict[str, object]:
    duplicate_pids = int(attributes["SITE_PID"].duplicated().sum())
    by_class: dict[str, object] = {}
    for pa_class, group in attributes.groupby("pa_class"):
        by_class[pa_class] = {
            "polygon_records": len(group),
            "distinct_sites": int(group["SITE_ID"].nunique()),
            "gis_area_km2_sum": round(float(group["GIS_AREA"].sum()), 1),
            "designations": dict(Counter(group["DESIG_ENG"]).most_common()),
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE,
        "source_version": SOURCE_VERSION,
        "polygon_records": len(attributes),
        "point_records_excluded": points,
        "duplicate_site_pid_records": duplicate_pids,
        "wildlife_layer_records_written": wildlife_written,
        "classes_loaded_to_postgis": list(LOADED_CLASSES),
        "wildlife_layer_note": "WDPA wildlife records are not loaded; the main wildlife layer comes from OpenStreetMap (phase11_load_osm.py).",
        "classes": by_class,
        "rules": {
            WILDLIFE_PA: "Designated/established National Park, Sanctuary, Wildlife Sanctuary variants, Conservation Reserve, Community Reserve.",
            FOREST: "Any non-proposed designation containing 'forest' (Reserve, Reserved, Protected, Unclassed Forest).",
            OTHER: "All other non-proposed designations (Ramsar, Biodiversity Heritage Site, Eco-Sensitive Zone, Biosphere Reserve, World Heritage, 'Protected').",
            PROPOSED: "Records with STATUS = Proposed, excluded from every protection metric.",
        },
        "caveats": [
            "WDPA coverage of Indian protected areas may be incomplete; this layer is not an official Government of India list.",
            "Point-only WDPA records have no boundary and are excluded from spatial intersection.",
            "gis_area_km2_sum adds polygon areas and double-counts overlapping parcels; it is not the protected land area.",
            "Overlap with any layer describes occurrence-record location, not habitat protection or management effectiveness.",
        ],
    }


def load_postgis() -> int:
    import psycopg
    import pyogrio

    loaded = 0
    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM protected_areas WHERE protected_area_id LIKE 'WDPA:%%' AND pa_class <> ALL(%s)",
                (list(LOADED_CLASSES),),
            )
            for path in polygon_layers():
                total = pyogrio.read_info(path)["features"]
                for start in range(0, total, BATCH_SIZE):
                    frame = pyogrio.read_dataframe(path, columns=ATTRIBUTE_COLUMNS, skip_features=start, max_features=BATCH_SIZE)
                    rows = [
                        {
                            "protected_area_id": f"WDPA:{record.SITE_PID}",
                            "wdpa_site_id": str(record.SITE_ID),
                            "name": record.NAME_ENG or f"WDPA site {record.SITE_ID}",
                            "designation": record.DESIG_ENG or None,
                            "designation_type": record.DESIG_TYPE or None,
                            "status": record.STATUS or None,
                            "status_year": int(record.STATUS_YR) if record.STATUS_YR else None,
                            "realm": record.REALM or None,
                            "reported_area": float(record.REP_AREA) if record.REP_AREA is not None else None,
                            "gis_area_km2": float(record.GIS_AREA) if record.GIS_AREA is not None else None,
                            "pa_class": classify(record.DESIG_ENG, record.STATUS),
                            "geometry": record.geometry.wkb,
                        }
                        for record in frame.itertuples(index=False)
                        if record.geometry is not None and classify(record.DESIG_ENG, record.STATUS) in LOADED_CLASSES
                    ]
                    cursor.executemany(
                        """INSERT INTO protected_areas
                        (protected_area_id, wdpa_site_id, name, designation, designation_type, status, status_year,
                         realm, reported_area, gis_area_km2, pa_class, source, source_version, geom)
                        VALUES (%(protected_area_id)s, %(wdpa_site_id)s, %(name)s, %(designation)s, %(designation_type)s,
                                %(status)s, %(status_year)s, %(realm)s, %(reported_area)s, %(gis_area_km2)s, %(pa_class)s,
                                %(source)s, %(source_version)s,
                                ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromWKB(%(geometry)s), 4326)), 3)))
                        ON CONFLICT (protected_area_id) DO UPDATE SET
                            name = EXCLUDED.name, designation = EXCLUDED.designation, status = EXCLUDED.status,
                            status_year = EXCLUDED.status_year, pa_class = EXCLUDED.pa_class,
                            source_version = EXCLUDED.source_version, geom = EXCLUDED.geom""",
                        [{**row, "source": SOURCE, "source_version": SOURCE_VERSION} for row in rows],
                    )
                    connection.commit()
                    loaded += len(rows)
                    print(f"  {path.parent.name}: {min(start + BATCH_SIZE, total)}/{total}")
    return loaded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Classify and write reports without touching PostGIS.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    attributes = read_attributes()
    wildlife_written = write_wildlife_layer()
    report = build_report(attributes, point_record_count(), wildlife_written)
    if not args.dry_run:
        report["postgis_records_loaded"] = load_postgis()
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "classes"}, indent=2))
    for pa_class, summary in report["classes"].items():
        print(f"{pa_class}: {summary['polygon_records']} polygons, {summary['distinct_sites']} sites, {summary['gis_area_km2_sum']} km2")


if __name__ == "__main__":
    main()
