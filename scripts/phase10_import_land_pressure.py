"""Import provenance-complete land-cover and forest-change observations by occurrence ID."""

from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import date
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "app" / "database" / "schema.sql"
REPORT = ROOT / "data" / "analytics" / "land_pressure_import_report.json"
EXCLUSIONS = ROOT / "data" / "analytics" / "land_pressure_import_exclusions.csv"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
REQUIRED_COLUMNS = {"occurrence_id", "land_cover_class", "land_cover_year", "source", "source_url", "retrieval_date", "spatial_resolution_m"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Authorized land-cover or forest-change CSV export.")
    return parser.parse_args()


def optional_float(value: str | None) -> float | None:
    return float(value) if value and value.strip() else None


def optional_int(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


def main() -> None:
    args = parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Missing required CSV columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    accepted: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA.read_text(encoding="utf-8"))
            cursor.execute("SELECT occurrence_id FROM occurrences")
            known_occurrences = {row[0] for row in cursor.fetchall()}
            for row in rows:
                try:
                    land_cover_year = int(row["land_cover_year"])
                    date.fromisoformat(row["retrieval_date"])
                    spatial_resolution_m = float(row["spatial_resolution_m"])
                    tree_cover_percent = optional_float(row.get("tree_cover_percent"))
                    loss_year = optional_int(row.get("tree_cover_loss_year"))
                except ValueError:
                    excluded.append({**row, "exclusion_reason": "invalid numeric field or retrieval_date"})
                    continue
                if row["occurrence_id"].strip() not in known_occurrences:
                    excluded.append({**row, "exclusion_reason": "occurrence_id is not in the quality-controlled occurrence table"})
                    continue
                if spatial_resolution_m <= 0 or tree_cover_percent is not None and not 0 <= tree_cover_percent <= 100:
                    excluded.append({**row, "exclusion_reason": "invalid spatial resolution or tree-cover percentage"})
                    continue
                accepted.append({
                    "occurrence_id": row["occurrence_id"].strip(),
                    "land_cover_class": row["land_cover_class"].strip(),
                    "land_cover_year": land_cover_year,
                    "tree_cover_percent": tree_cover_percent,
                    "tree_cover_loss_year": loss_year,
                    "source": row["source"].strip(),
                    "source_url": row["source_url"].strip(),
                    "retrieval_date": row["retrieval_date"].strip(),
                    "spatial_resolution_m": spatial_resolution_m,
                    "license": row.get("license") or None,
                })
            cursor.executemany(
                """INSERT INTO occurrence_land_pressure
                (occurrence_id, land_cover_class, land_cover_year, tree_cover_percent, tree_cover_loss_year,
                 source, source_url, retrieval_date, spatial_resolution_m, license)
                VALUES (%(occurrence_id)s, %(land_cover_class)s, %(land_cover_year)s, %(tree_cover_percent)s, %(tree_cover_loss_year)s,
                        %(source)s, %(source_url)s, %(retrieval_date)s, %(spatial_resolution_m)s, %(license)s)
                ON CONFLICT (occurrence_id) DO UPDATE SET
                    land_cover_class = EXCLUDED.land_cover_class,
                    land_cover_year = EXCLUDED.land_cover_year,
                    tree_cover_percent = EXCLUDED.tree_cover_percent,
                    tree_cover_loss_year = EXCLUDED.tree_cover_loss_year,
                    source = EXCLUDED.source,
                    source_url = EXCLUDED.source_url,
                    retrieval_date = EXCLUDED.retrieval_date,
                    spatial_resolution_m = EXCLUDED.spatial_resolution_m,
                    license = EXCLUDED.license""",
                accepted,
            )

    REPORT.write_text(json.dumps({"input_rows": len(rows), "accepted_rows": len(accepted), "excluded_rows": len(excluded)}, indent=2), encoding="utf-8")
    with EXCLUSIONS.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list((rows[0].keys() if rows else REQUIRED_COLUMNS)) + ["exclusion_reason"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(excluded)
    print(f"Imported {len(accepted)} land-pressure records; excluded {len(excluded)} rows.")


if __name__ == "__main__":
    main()
