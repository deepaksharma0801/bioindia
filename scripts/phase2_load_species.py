"""Phase 2: upsert the platform species list into PostGIS before any occurrences are loaded.

Taxonomy comes from the IUCN export (title-cased) for IUCN species; the flagships keep the GBIF
taxonomy already in the database. phase4_load_postgis.py later refreshes every species with the
GBIF Backbone taxonomy from the occurrence download.
"""

from __future__ import annotations

import csv
import json
import os

import psycopg

from db_schema import ensure_schema
from phase4_load_postgis import SPECIES_COLUMNS
from phase4_prepare_postgis_inputs import IUCN_DIR, PROCESSED, load_species, species_master


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
SOURCE_IDENTIFIER = "GBIF species-match API (species list built before the occurrence download)"


def iucn_taxonomy(species: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    by_taxon = {}
    with (IUCN_DIR / "taxonomy.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_taxon[row["internalTaxonId"]] = {
                "kingdom": row["kingdomName"].title(), "phylum": row["phylumName"].title(), "class": row["className"].title(),
                "order": row["orderName"].title(), "family": row["familyName"].title(), "genus": row["genusName"],
            }
    return {item["gbif_species_key"]: by_taxon[item["iucn_taxon_id"]] for item in species if item["iucn_taxon_id"] in by_taxon}


def main() -> None:
    ensure_schema(DATABASE_URL)
    species = load_species()
    master = species_master(species, iucn_taxonomy(species), SOURCE_IDENTIFIER)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            existing = {row[0] for row in cursor.execute("SELECT species_id FROM species").fetchall()}
            names = ", ".join(SPECIES_COLUMNS)
            values = ", ".join(f"%({column})s" for column in SPECIES_COLUMNS)
            # Existing rows (the flagships) keep their GBIF taxonomy and source; only new species are inserted here.
            cursor.executemany(
                f"INSERT INTO species ({names}) VALUES ({values}) ON CONFLICT (species_id) DO NOTHING",
                [row for row in master if row["species_id"] not in existing],
            )
            total = cursor.execute("SELECT COUNT(*) FROM species").fetchone()[0]
    (PROCESSED / "species_master_pre_download.json").write_text(json.dumps(master, indent=2), encoding="utf-8")
    print(f"Inserted {len([r for r in master if r['species_id'] not in existing])} new species; {total} species in the database.")


if __name__ == "__main__":
    main()
