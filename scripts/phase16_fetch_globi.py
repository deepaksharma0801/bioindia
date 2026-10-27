"""Phase 16: fetch documented biotic interactions for every platform species from GloBI.

Queries https://api.globalbioticinteractions.org for interactions where the species is the source
and where it is the target. Raw responses are cached per species in data/raw/globi/, so a stopped
run resumes. Loading into PostGIS is done by phase16_load_interactions.py.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import date
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
SPECIES_LIST = ROOT / "data" / "processed" / "species_list.csv"
CACHE = ROOT / "data" / "raw" / "globi"
API = "https://api.globalbioticinteractions.org/interaction"
HEADERS = {"User-Agent": "BioIndia-MSc-research/0.2"}
LIMIT = 5000
FIELDS = [
    "source_taxon_name", "source_taxon_path", "interaction_type", "target_taxon_name", "target_taxon_path",
    "study_citation", "study_source_citation", "study_url",
]


def query(direction: str, name: str) -> list[dict[str, object]]:
    params = [(direction, name), ("type", "json.v2"), ("limit", str(LIMIT))] + [("field", field) for field in FIELDS]
    for attempt in range(4):
        try:
            response = requests.get(API, params=params, headers=HEADERS, timeout=120)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GloBI query failed: {direction}={name}")


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with SPECIES_LIST.open(encoding="utf-8") as handle:
        species = list(csv.DictReader(handle))
    for position, item in enumerate(species, start=1):
        path = CACHE / f"{item['species_id']}.json"
        if path.exists():
            continue
        names = sorted({item["scientific_name"], item["gbif_accepted_name"]} - {""})
        rows, truncated = [], []
        for name in names:
            for direction in ("sourceTaxon", "targetTaxon"):
                result = query(direction, name)
                rows.extend(result)
                if len(result) >= LIMIT:
                    truncated.append(f"{direction}={name}")
                time.sleep(0.5)
        path.write_text(json.dumps({
            "species_id": item["species_id"], "names_queried": names, "retrieved_at": date.today().isoformat(),
            "truncated_queries": truncated, "rows": rows,
        }), encoding="utf-8")
        print(f"  {position}/{len(species)} {item['scientific_name']}: {len(rows)} rows", flush=True)


if __name__ == "__main__":
    main()
