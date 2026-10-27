"""Convert the IUCN Red List export in the project folder into the import format of
phase8_import_conservation_assessments.py (one row per global assessment, with provenance).

Input:  0433e6f8-919d-4ab4-ba8a-6bc57065b07b/ (assessments, threats, habitats, conservation_needed)
Output: data/processed/iucn_assessments_import.csv
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IUCN_DIR = ROOT / "0433e6f8-919d-4ab4-ba8a-6bc57065b07b"
OUTPUT = ROOT / "data" / "processed" / "iucn_assessments_import.csv"
# Date of the files inside the export archive (0433e6f8-...zip); the export has no other date stamp.
RETRIEVAL_DATE = "2026-10-21"
DATASET_VERSION = f"IUCN Red List export retrieved {RETRIEVAL_DATE}"
COLUMNS = [
    "scientific_name", "iucn_taxon_id", "iucn_category", "assessment_year", "population_trend", "threat_codes",
    "threat_descriptions", "habitat_codes", "conservation_actions", "assessment_version", "source_url",
    "dataset_version", "retrieval_date",
]


def read(name: str) -> list[dict[str, str]]:
    with (IUCN_DIR / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def grouped(name: str, field: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for row in read(name):
        if row[field] and row[field] not in values[row["assessmentId"]]:
            values[row["assessmentId"]].append(row[field])
    return values


def main() -> None:
    threat_codes, threat_names = grouped("threats.csv", "code"), grouped("threats.csv", "name")
    habitats, actions = grouped("habitats.csv", "code"), grouped("conservation_needed.csv", "name")
    rows = []
    for assessment in read("assessments.csv"):
        if "Global" not in assessment["scopes"].split(", "):
            continue
        assessment_id = assessment["assessmentId"]
        rows.append({
            "scientific_name": assessment["scientificName"],
            "iucn_taxon_id": assessment["internalTaxonId"],
            "iucn_category": assessment["redlistCategory"],
            "assessment_year": assessment["yearPublished"],
            "population_trend": assessment["populationTrend"] or None,
            "threat_codes": "; ".join(threat_codes[assessment_id]),
            "threat_descriptions": "; ".join(threat_names[assessment_id]),
            "habitat_codes": "; ".join(habitats[assessment_id]),
            "conservation_actions": "; ".join(actions[assessment_id]),
            "assessment_version": f"assessment {assessment_id}, criteria {assessment['criteriaVersion']}",
            "source_url": f"https://www.iucnredlist.org/species/{assessment['internalTaxonId']}/{assessment_id}",
            "dataset_version": DATASET_VERSION,
            "retrieval_date": RETRIEVAL_DATE,
        })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} global assessments to {OUTPUT}")


if __name__ == "__main__":
    main()
