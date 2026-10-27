"""Phase 2: build the platform species list and match it to the GBIF Backbone Taxonomy.

Species = the India-native, extant species in the IUCN Red List export, plus the five flagship
species. Each name is matched with GBIF's species-match API; only exact or confident fuzzy
matches at species rank are accepted. Everything else goes to a review log, not into the list.

Output: data/processed/species_list.csv          accepted species with GBIF and IUCN identifiers
        data/analytics/taxonomy_match_review.csv  rejected or ambiguous matches
        data/analytics/taxonomy_match_report.json
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
IUCN_DIR = ROOT / "0433e6f8-919d-4ab4-ba8a-6bc57065b07b"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
GBIF_API = "https://api.gbif.org/v1"
HEADERS = {"User-Agent": "BioIndia-MSc-research/0.2"}
MIN_FUZZY_CONFIDENCE = 95

# Stable platform IDs used by the dashboard; every other species gets an ID from its name.
FLAGSHIPS = {
    "Panthera tigris": "tiger",
    "Elephas maximus": "elephant",
    "Rhinoceros unicornis": "rhino",
    "Melursus ursinus": "bear",
    "Crocodylus palustris": "croc",
}
KINGDOM = {"ANIMALIA": "Animalia", "PLANTAE": "Plantae", "FUNGI": "Fungi"}


def read_csv(name: str) -> list[dict[str, str]]:
    with (IUCN_DIR / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def iucn_india_species() -> list[dict[str, str]]:
    native = {
        row["internalTaxonId"] for row in read_csv("countries.csv")
        if row["code"] == "IN" and row["origin"] == "Native" and row["presence"] in {"Extant", "Possibly Extant"}
    }
    taxonomy = {row["internalTaxonId"]: row for row in read_csv("taxonomy.csv")}
    category = {row["internalTaxonId"]: row["redlistCategory"] for row in read_csv("assessments.csv") if "Global" in row["scopes"]}
    species = []
    for taxon_id in sorted(native):
        row = taxonomy[taxon_id]
        name = f"{row['genusName']} {row['speciesName']}"
        species.append({
            "scientific_name": name,
            "kingdom": KINGDOM.get(row["kingdomName"], row["kingdomName"].title()),
            "iucn_taxon_id": taxon_id,
            "iucn_category_in_export": category.get(taxon_id, ""),
            "origin": "IUCN export (India native, extant)",
        })
    return species


def match(name: str, kingdom: str | None) -> dict[str, object]:
    params = {"name": name, "rank": "SPECIES"}
    if kingdom:
        params["kingdom"] = kingdom
    for attempt in range(3):
        try:
            response = requests.get(f"{GBIF_API}/species/match", params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GBIF species match failed for {name}")


def india_record_count(taxon_key: int) -> int:
    response = requests.get(
        f"{GBIF_API}/occurrence/search",
        params={"taxonKey": taxon_key, "country": "IN", "limit": 0},
        headers=HEADERS, timeout=30,
    )
    response.raise_for_status()
    return int(response.json()["count"])


def species_id(name: str, used: set[str]) -> str:
    if name in FLAGSHIPS:
        return FLAGSHIPS[name]
    base = name.lower().replace(" ", "_")
    candidate, suffix = base, 2
    while candidate in used:
        candidate, suffix = f"{base}_{suffix}", suffix + 1
    return candidate


def main() -> None:
    candidates = iucn_india_species()
    names = {item["scientific_name"] for item in candidates}
    for name in FLAGSHIPS:
        if name not in names:
            candidates.append({"scientific_name": name, "kingdom": "Animalia", "iucn_taxon_id": "", "iucn_category_in_export": "", "origin": "Flagship species"})

    accepted, review, used_ids, used_keys = [], [], set(), {}
    for item in candidates:
        result = match(item["scientific_name"], item["kingdom"])
        match_type, confidence = result.get("matchType"), int(result.get("confidence") or 0)
        key = result.get("speciesKey") or (result.get("usageKey") if result.get("rank") == "SPECIES" else None)
        reason = None
        if match_type == "NONE" or not key:
            reason = "no_species_level_match"
        elif match_type == "HIGHERRANK":
            reason = "matched_only_higher_rank"
        elif match_type == "FUZZY" and confidence < MIN_FUZZY_CONFIDENCE:
            reason = f"fuzzy_match_confidence_{confidence}"
        elif key in used_keys:
            reason = f"same_gbif_species_as_{used_keys[key]}"
        record = {
            **item,
            "gbif_species_key": key,
            "gbif_accepted_name": result.get("species") or result.get("canonicalName"),
            "gbif_status": result.get("status"),
            "match_type": match_type,
            "match_confidence": confidence,
        }
        if reason:
            review.append({**record, "review_reason": reason})
            continue
        record["species_id"] = species_id(item["scientific_name"], used_ids)
        record["india_gbif_records"] = india_record_count(key)
        used_ids.add(record["species_id"])
        used_keys[key] = item["scientific_name"]
        accepted.append(record)
        time.sleep(0.2)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    columns = ["species_id", "scientific_name", "gbif_accepted_name", "gbif_species_key", "gbif_status", "match_type",
               "match_confidence", "kingdom", "iucn_taxon_id", "iucn_category_in_export", "origin", "india_gbif_records"]
    with (PROCESSED / "species_list.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(accepted, key=lambda r: r["scientific_name"]))
    with (ANALYTICS / "taxonomy_match_review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[c for c in columns if c not in {"species_id", "india_gbif_records"}] + ["review_reason"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(review)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": len(candidates),
        "accepted": len(accepted),
        "sent_to_review": len(review),
        "review_reasons": dict(Counter(r["review_reason"] for r in review)),
        "match_types_accepted": dict(Counter(r["match_type"] for r in accepted)),
        "species_without_india_records": sum(1 for r in accepted if r["india_gbif_records"] == 0),
        "india_records_total": sum(r["india_gbif_records"] for r in accepted),
        "largest": sorted(((r["scientific_name"], r["india_gbif_records"]) for r in accepted), key=lambda x: -x[1])[:10],
        "rule": f"accept EXACT, or FUZZY with confidence >= {MIN_FUZZY_CONFIDENCE}, at species rank; never two names to one GBIF species",
    }
    (ANALYTICS / "taxonomy_match_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
