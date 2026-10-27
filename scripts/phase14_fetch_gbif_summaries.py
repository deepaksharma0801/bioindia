"""Phase 14 input: per-species India summaries from the GBIF occurrence search facets (no record download).

For every platform species this asks GBIF for counts by year, GADM state and district, basis of
record and dataset. The summaries give range and recording-history features in minutes, so the
risk model does not have to wait for the full occurrence download.

Output: data/raw/gbif/summaries/<species_id>.json and data/processed/gbif_species_summaries.json
"""

from __future__ import annotations

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
SPECIES_LIST = ROOT / "data" / "processed" / "species_list.csv"
CACHE = ROOT / "data" / "raw" / "gbif" / "summaries"
OUTPUT = ROOT / "data" / "processed" / "gbif_species_summaries.json"
API = "https://api.gbif.org/v1/occurrence/search"
HEADERS = {"User-Agent": "BioIndia-MSc-research/0.2"}
FACETS = ["year", "gadmLevel1Gid", "gadmLevel2Gid", "basisOfRecord", "datasetKey"]


def fetch(item: dict[str, str]) -> dict[str, object]:
    path = CACHE / f"{item['species_id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    params = [("taxonKey", item["gbif_species_key"]), ("country", "IN"), ("limit", "0"), ("facetLimit", "1000"),
              ("hasCoordinate", "true"), ("hasGeospatialIssue", "false"), ("occurrenceStatus", "PRESENT")]
    params += [("facet", facet) for facet in FACETS]
    for attempt in range(4):
        try:
            response = requests.get(API, params=params, headers=HEADERS, timeout=60)
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, ValueError):
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"GBIF summary failed for {item['scientific_name']}")
    summary = {
        "species_id": item["species_id"],
        "gbif_species_key": item["gbif_species_key"],
        "retrieved_at": date.today().isoformat(),
        "filters": "country=IN, hasCoordinate, no geospatial issue, occurrenceStatus=PRESENT",
        "count": payload["count"],
        "facets": {facet["field"]: {row["name"]: row["count"] for row in facet["counts"]} for facet in payload.get("facets", [])},
    }
    path.write_text(json.dumps(summary), encoding="utf-8")
    return summary


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with SPECIES_LIST.open(encoding="utf-8") as handle:
        species = list(csv.DictReader(handle))
    with ThreadPoolExecutor(max_workers=6) as pool:
        summaries = list(pool.map(fetch, species))
    OUTPUT.write_text(json.dumps(summaries), encoding="utf-8")
    print(f"Wrote {len(summaries)} species summaries to {OUTPUT}; {sum(1 for s in summaries if s['count'])} with India records")


if __name__ == "__main__":
    main()
