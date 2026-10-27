"""Parse the supplied NTCA KML and idempotently load its polygon features into PostGIS."""

from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
KML = ROOT / "data" / "raw" / "protected_areas" / "extracted" / "PA_TR_Corridor_Final.kml"
REPORT = ROOT / "data" / "analytics" / "protected_area_load_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
KML_NS = "{http://www.opengis.net/kml/2.2}"


def coordinates(text: str | None) -> list[list[float]]:
    return [[float(value) for value in point.split(",")[:2]] for point in (text or "").split()]


def main() -> None:
    root = ET.parse(KML).getroot()
    rows: list[dict[str, object]] = []
    skipped = 0
    for placemark in root.iter(f"{KML_NS}Placemark"):
        name = (placemark.findtext(f"{KML_NS}name") or "").strip()
        properties = {item.attrib.get("name", ""): (item.text or "").strip() for item in placemark.iter(f"{KML_NS}SimpleData")}
        polygons: list[list[list[list[float]]]] = []
        for polygon in placemark.iter(f"{KML_NS}Polygon"):
            rings = [coordinates(item.text) for item in polygon.iter(f"{KML_NS}coordinates")]
            rings = [ring for ring in rings if len(ring) >= 4]
            if rings:
                polygons.append(rings)
        if not name or not polygons:
            skipped += 1
            continue
        area_value = properties.get("REP_AREA") or None
        rows.append({
            "protected_area_id": hashlib.sha256((name + json.dumps(polygons, separators=(",", ":"))).encode("utf-8")).hexdigest(),
            "name": name,
            "designation": properties.get("DESIG") or None,
            "state_name": properties.get("state_name") or None,
            "reported_area": float(area_value) if area_value else None,
            "source": "NTCA PA_TR_Corridor_Final KML",
            "geometry": json.dumps({"type": "MultiPolygon", "coordinates": polygons}),
        })

    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO protected_areas (protected_area_id, name, designation, state_name, reported_area, source, geom)
                VALUES (%(protected_area_id)s, %(name)s, %(designation)s, %(state_name)s, %(reported_area)s, %(source)s,
                        ST_SetSRID(ST_GeomFromGeoJSON(%(geometry)s), 4326))
                ON CONFLICT (protected_area_id) DO UPDATE SET
                    name = EXCLUDED.name, designation = EXCLUDED.designation, state_name = EXCLUDED.state_name,
                    reported_area = EXCLUDED.reported_area, geom = EXCLUDED.geom""",
                rows,
            )
    REPORT.write_text(json.dumps({"source": str(KML), "loaded_features": len(rows), "skipped_features": skipped}, indent=2), encoding="utf-8")
    print(f"Loaded {len(rows)} protected-area features; skipped {skipped} placemarks.")


if __name__ == "__main__":
    main()
