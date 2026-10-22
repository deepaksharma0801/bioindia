"""Idempotently load prepared species and occurrence data into PostGIS."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SCHEMA = ROOT / "backend" / "app" / "database" / "schema.sql"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

SPECIES_COLUMNS = [
    "species_id", "scientific_name", "canonical_name", "common_name", "kingdom", "phylum", "class_name",
    "order_name", "family", "genus", "species_epithet", "gbif_taxon_key", "iucn_taxon_id", "native_status",
    "endemic_status", "environment_type", "current_iucn_status", "current_iucn_status_source", "source",
    "source_dataset_identifier", "license",
]
OCCURRENCE_COLUMNS = [
    "occurrence_id", "species_id", "scientific_name_original", "latitude", "longitude", "coordinate_uncertainty",
    "coordinate_uncertainty_class", "event_date", "date_precision", "year", "month", "state", "basis_of_record",
    "dataset_key", "source", "source_record_id", "license", "quality_flags", "gbif_issues", "source_download_doi",
]


def upsert_sql(table: str, columns: list[str], key: str, extra_columns: str = "", extra_values: str = "") -> str:
    names = ", ".join(columns) + extra_columns
    values = ", ".join(f"%({column})s" for column in columns) + extra_values
    updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column != key)
    if extra_columns:
        updates += ", geom = EXCLUDED.geom"
    return f"INSERT INTO {table} ({names}) VALUES ({values}) ON CONFLICT ({key}) DO UPDATE SET {updates}"


def main() -> None:
    species = json.loads((PROCESSED / "species_master.json").read_text(encoding="utf-8"))
    with (PROCESSED / "occurrences_clean.jsonl").open(encoding="utf-8") as handle:
        occurrences = [json.loads(line) for line in handle if line.strip()]
    sources = sorted({record["source"] for record in occurrences})
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(SCHEMA.read_text(encoding="utf-8"))
            cursor.executemany(upsert_sql("species", SPECIES_COLUMNS, "species_id"), species)
            cursor.executemany(
                upsert_sql(
                    "occurrences", OCCURRENCE_COLUMNS, "occurrence_id",
                    extra_columns=", geom",
                    extra_values=", ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)",
                ),
                occurrences,
            )
            # Remove records from the same sources that the latest quality screen no longer accepts.
            cursor.execute(
                "DELETE FROM occurrences WHERE source = ANY(%s) AND NOT (occurrence_id = ANY(%s))",
                (sources, [record["occurrence_id"] for record in occurrences]),
            )
            removed = cursor.rowcount
        print(f"Loaded {len(species)} species and {len(occurrences)} occurrences; removed {removed} stale occurrences.")


if __name__ == "__main__":
    main()
