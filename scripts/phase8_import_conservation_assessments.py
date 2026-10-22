"""Idempotently import authorized, provenance-complete conservation assessments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "backend" / "app" / "database" / "schema.sql"
REPORT = ROOT / "data" / "analytics" / "conservation_import_report.json"
UNMATCHED = ROOT / "data" / "analytics" / "conservation_import_unmatched.csv"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
REQUIRED_COLUMNS = {"scientific_name", "iucn_category", "assessment_year", "assessment_version", "source_url", "retrieval_date"}
VALID_CATEGORIES = {"EX", "EW", "CR", "EN", "VU", "NT", "LC", "DD", "NE"}


def list_value(value: str | None) -> list[str] | None:
    values = [item.strip() for item in (value or "").split(";") if item.strip()]
    return values or None


def assessment_id(row: dict[str, str], species_id: str) -> str:
    material = "|".join((species_id, row["assessment_version"], row["source_url"]))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Authorized conservation-assessment CSV export.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise SystemExit(f"Missing required CSV columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    accepted: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA.read_text(encoding="utf-8"))
            cursor.execute("SELECT species_id, scientific_name FROM species")
            species_by_name = {name.casefold(): species_id for species_id, name in cursor.fetchall()}
            for row in rows:
                category = row["iucn_category"].strip().upper()
                species_id = species_by_name.get(row["scientific_name"].strip().casefold())
                try:
                    year = int(row["assessment_year"])
                    date.fromisoformat(row["retrieval_date"])
                except ValueError:
                    excluded.append({**row, "exclusion_reason": "invalid assessment_year or retrieval_date"})
                    continue
                if category not in VALID_CATEGORIES:
                    excluded.append({**row, "exclusion_reason": "unsupported IUCN category"})
                    continue
                if not species_id:
                    excluded.append({**row, "exclusion_reason": "scientific name is not in the species master"})
                    continue
                accepted.append(
                    {
                        "assessment_id": assessment_id(row, species_id),
                        "species_id": species_id,
                        "iucn_taxon_id": row.get("iucn_taxon_id") or None,
                        "iucn_category": category,
                        "assessment_year": year,
                        "population_trend": row.get("population_trend") or None,
                        "threat_codes": json.dumps(list_value(row.get("threat_codes"))),
                        "threat_descriptions": json.dumps(list_value(row.get("threat_descriptions"))),
                        "habitat_codes": json.dumps(list_value(row.get("habitat_codes"))),
                        "conservation_actions": json.dumps(list_value(row.get("conservation_actions"))),
                        "assessment_version": row["assessment_version"].strip(),
                        "source": "IUCN Red List authorized import",
                        "source_url": row["source_url"].strip(),
                        "dataset_version": row.get("dataset_version") or None,
                        "retrieval_date": row["retrieval_date"].strip(),
                    }
                )
            cursor.executemany(
                """INSERT INTO conservation_assessments
                (assessment_id, species_id, iucn_taxon_id, iucn_category, assessment_year, population_trend,
                 threat_codes, threat_descriptions, habitat_codes, conservation_actions, assessment_version,
                 source, source_url, dataset_version, retrieval_date)
                VALUES (%(assessment_id)s, %(species_id)s, %(iucn_taxon_id)s, %(iucn_category)s, %(assessment_year)s, %(population_trend)s,
                        %(threat_codes)s::jsonb, %(threat_descriptions)s::jsonb, %(habitat_codes)s::jsonb, %(conservation_actions)s::jsonb,
                        %(assessment_version)s, %(source)s, %(source_url)s, %(dataset_version)s, %(retrieval_date)s)
                ON CONFLICT (assessment_id) DO UPDATE SET
                    iucn_category = EXCLUDED.iucn_category,
                    assessment_year = EXCLUDED.assessment_year,
                    population_trend = EXCLUDED.population_trend,
                    threat_codes = EXCLUDED.threat_codes,
                    threat_descriptions = EXCLUDED.threat_descriptions,
                    habitat_codes = EXCLUDED.habitat_codes,
                    conservation_actions = EXCLUDED.conservation_actions,
                    retrieval_date = EXCLUDED.retrieval_date,
                    imported_at = NOW()""",
                accepted,
            )

    REPORT.write_text(json.dumps({"input_rows": len(rows), "accepted_rows": len(accepted), "excluded_rows": len(excluded)}, indent=2), encoding="utf-8")
    with UNMATCHED.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list((rows[0].keys() if rows else REQUIRED_COLUMNS)) + ["exclusion_reason"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(excluded)
    print(f"Imported {len(accepted)} assessments; excluded {len(excluded)} rows.")


if __name__ == "__main__":
    main()
