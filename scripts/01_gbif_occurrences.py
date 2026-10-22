"""
SCRIPT 01 — GBIF Occurrence Data Collector
===========================================
Run this on YOUR OWN machine (requires internet access to api.gbif.org).
No GBIF account needed for basic occurrence queries.

Prerequisites:
    pip install requests pandas tqdm

What it does:
    - Reads species_list.csv (from Script 00)
    - For each species, queries GBIF occurrence API filtered to India
    - Saves raw occurrence points (lat, lon, state, year) to:
        data/occurrences_raw.csv
    - Saves aggregated counts per (species x state) to:
        data/occurrences_by_state.csv
    - Saves annual trend counts (1999-2024) per species to:
        data/occurrences_by_year.csv

Run: python 01_gbif_occurrences.py
"""

import requests
import pandas as pd
import time
import os
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

# ── Load species list ────────────────────────────────────────
species_df = pd.read_csv("data/species_list.csv")
print(f"Loaded {len(species_df)} species")

# ── GBIF API settings ────────────────────────────────────────
GBIF_BASE = "https://api.gbif.org/v1"
HEADERS = {"User-Agent": "BioIndia-Research/1.0 (conservation data collection)"}
COUNTRY = "IN"
LIMIT = 300          # records per page (GBIF max is 300)
YEAR_START = 1999
YEAR_END = 2024

# ── State name normalizer ────────────────────────────────────
# Maps common GBIF state name variants to the exact names used in STATE_DB
STATE_NAME_MAP = {
    "Orissa": "Odisha",
    "Uttaranchal": "Uttarakhand",
    "Pondicherry": "Puducherry",
    "Jammu And Kashmir": "Jammu & Kashmir",
    "Andaman And Nicobar Islands": "Andaman & Nicobar",
    "Daman And Diu": "Daman & Diu",
    "Dadra And Nagar Haveli": "Dadra & Nagar Haveli",
    "Delhi": "Delhi",
    "NCT Of Delhi": "Delhi",
}

def normalize_state(name):
    if not name:
        return None
    name = str(name).strip()
    return STATE_NAME_MAP.get(name, name)


def get_gbif_taxon_key(scientific_name):
    """Fetch the GBIF taxon key for a given scientific name."""
    url = f"{GBIF_BASE}/species/match"
    params = {"name": scientific_name, "kingdom": "Animalia"}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("matchType") not in ("NONE", None):
                return data.get("usageKey")
    except Exception as e:
        print(f"  ⚠ Taxon key lookup failed for {scientific_name}: {e}")
    # Try without kingdom filter (for plants)
    try:
        r = requests.get(url, params={"name": scientific_name}, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("matchType") not in ("NONE", None):
                return data.get("usageKey")
    except Exception as e:
        print(f"  ⚠ Second taxon key lookup failed: {e}")
    return None


def fetch_occurrences(taxon_key, species_id, scientific_name):
    """Fetch all occurrence records for a taxon key in India."""
    records = []
    offset = 0

    while True:
        params = {
            "taxonKey": taxon_key,
            "country": COUNTRY,
            "hasCoordinate": True,
            "hasGeospatialIssue": False,
            "year": f"{YEAR_START},{YEAR_END}",
            "limit": LIMIT,
            "offset": offset,
        }
        try:
            r = requests.get(
                f"{GBIF_BASE}/occurrence/search",
                params=params,
                headers=HEADERS,
                timeout=30
            )
            if r.status_code != 200:
                print(f"  ⚠ HTTP {r.status_code} for {scientific_name}")
                break

            data = r.json()
            results = data.get("results", [])
            if not results:
                break

            for rec in results:
                lat = rec.get("decimalLatitude")
                lon = rec.get("decimalLongitude")
                if lat is None or lon is None:
                    continue
                # Bounding box for India (rough)
                if not (6.5 <= lat <= 37.5 and 68.0 <= lon <= 98.0):
                    continue

                records.append({
                    "species_id": species_id,
                    "scientific_name": scientific_name,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                    "state": normalize_state(rec.get("stateProvince")),
                    "year": rec.get("year"),
                    "month": rec.get("month"),
                    "source": "GBIF",
                    "record_quality": rec.get("basisOfRecord"),
                    "gbif_key": rec.get("key"),
                })

            if data.get("endOfRecords", True):
                break

            offset += LIMIT
            time.sleep(0.5)   # be polite to the API

        except requests.exceptions.Timeout:
            print(f"  ⚠ Timeout at offset {offset} for {scientific_name}")
            break
        except Exception as e:
            print(f"  ⚠ Error at offset {offset}: {e}")
            break

    return records


# ── Main collection loop ─────────────────────────────────────
all_records = []

for _, row in tqdm(species_df.iterrows(), total=len(species_df), desc="Fetching species"):
    sp_id = row["species_id"]
    sci_name = row["scientific_name"]
    
    # Skip truly extinct species (no occurrences expected from GBIF)
    if row["iucn_category"] in ("EX", "EX_India"):
        print(f"  ⏭ Skipping truly extinct: {sci_name}")
        continue

    print(f"\n→ {sci_name} ({sp_id})")

    # Step 1: Get GBIF taxon key
    key = get_gbif_taxon_key(sci_name)
    if not key:
        print(f"  ⚠ No GBIF taxon key found — skipping")
        continue
    print(f"  GBIF taxon key: {key}")

    # Step 2: Fetch occurrences
    records = fetch_occurrences(key, sp_id, sci_name)
    print(f"  Found {len(records)} valid occurrence records")
    all_records.extend(records)

    time.sleep(1.0)   # rate limit


# ── Save raw occurrences ─────────────────────────────────────
raw_df = pd.DataFrame(all_records)
raw_df.to_csv("data/occurrences_raw.csv", index=False)
print(f"\n✅ Saved {len(raw_df)} raw occurrences to data/occurrences_raw.csv")


# ── Aggregate by (species x state) ──────────────────────────
if not raw_df.empty:
    state_agg = (
        raw_df.dropna(subset=["state"])
        .groupby(["species_id", "scientific_name", "state"])
        .size()
        .reset_index(name="obs_count")
    )
    state_agg.to_csv("data/occurrences_by_state.csv", index=False)
    print(f"✅ Saved state aggregates to data/occurrences_by_state.csv")

    # ── Aggregate by (species x year) for trend arrays ──────
    year_agg = (
        raw_df.dropna(subset=["year"])
        .assign(year=lambda d: d["year"].astype(int))
        .query(f"{YEAR_START} <= year <= {YEAR_END}")
        .groupby(["species_id", "scientific_name", "year"])
        .size()
        .reset_index(name="record_count")
    )

    # Pivot to wide format (one column per year)
    year_pivot = year_agg.pivot_table(
        index=["species_id", "scientific_name"],
        columns="year",
        values="record_count",
        fill_value=0
    ).reset_index()
    year_pivot.columns = [
        str(c) if isinstance(c, int) else c for c in year_pivot.columns
    ]
    # Ensure all years 1999-2024 are present as columns
    for yr in range(YEAR_START, YEAR_END + 1):
        if str(yr) not in year_pivot.columns:
            year_pivot[str(yr)] = 0

    year_pivot.to_csv("data/occurrences_by_year.csv", index=False)
    print(f"✅ Saved annual trends to data/occurrences_by_year.csv")

print("\nDone. Next: run 02_iucn_data.py")
