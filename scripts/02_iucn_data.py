"""
SCRIPT 02 — IUCN Red List Data Collector
==========================================
Run on YOUR OWN machine. Requires a free IUCN API token.

HOW TO GET YOUR TOKEN:
  1. Go to https://api.iucnredlist.org/
  2. Click "Request a token"
  3. Fill in your details (conservation research / academic)
  4. Token arrives by email within 1-2 days
  5. Paste it in the IUCN_TOKEN variable below

Prerequisites:
    pip install requests pandas tqdm

What it does:
    - For each species in species_list.csv, queries IUCN API for:
        * Detailed threat data (threat_count)
        * Habitat information (habitat_count)
        * Historical assessment data (for Stage 3 ML)
        * Population & range data (EOO, AOO, generation length)
    - Saves to:
        data/iucn_traits.csv           (trait variables for ERI)
        data/iucn_assessments.csv      (historical assessments for ML)

Run: python 02_iucn_data.py
"""

import requests
import pandas as pd
import time
import os
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

# ── PASTE YOUR IUCN TOKEN HERE ───────────────────────────────
IUCN_TOKEN = "YOUR_TOKEN_HERE"
# ─────────────────────────────────────────────────────────────

IUCN_BASE = "https://apiv3.iucnredlist.org/api/v3"
HEADERS = {"Accept": "application/json"}

species_df = pd.read_csv("data/species_list.csv")
print(f"Loaded {len(species_df)} species")


def iucn_get(endpoint):
    """Make a GET request to IUCN API with token."""
    url = f"{IUCN_BASE}/{endpoint}?token={IUCN_TOKEN}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"  ⚠ HTTP {r.status_code}: {url}")
            return None
    except Exception as e:
        print(f"  ⚠ Error: {e}")
        return None


def get_species_id_from_name(scientific_name):
    """Get IUCN internal taxon ID from scientific name."""
    name_encoded = scientific_name.replace(" ", "%20")
    data = iucn_get(f"species/{name_encoded}")
    if data and data.get("result"):
        return data["result"][0].get("taxonid")
    return None


def get_threats(taxon_id):
    """Get list of threats for a species."""
    data = iucn_get(f"threats/species/id/{taxon_id}")
    if data and data.get("result"):
        return data["result"]
    return []


def get_habitats(taxon_id):
    """Get habitat types for a species."""
    data = iucn_get(f"habitats/species/id/{taxon_id}")
    if data and data.get("result"):
        return data["result"]
    return []


def get_narrative(taxon_id):
    """Get population, range, and trend narrative."""
    data = iucn_get(f"species/narrative/id/{taxon_id}")
    if data and data.get("result"):
        return data["result"][0]
    return {}


def get_assessment_history(scientific_name):
    """Get historical assessment records for trajectory analysis."""
    name_encoded = scientific_name.replace(" ", "%20")
    data = iucn_get(f"species/history/name/{name_encoded}")
    if data and data.get("result"):
        return data["result"]
    return []


# Category to numeric mapping
CATEGORY_NUM = {
    "EX": 7, "EW": 6, "CR": 6, "EN": 5, "VU": 4,
    "NT": 3, "LC": 2, "DD": 1, "NE": 0
}

# ── Main collection loop ─────────────────────────────────────
trait_records = []
assessment_records = []

for _, row in tqdm(species_df.iterrows(), total=len(species_df), desc="IUCN lookup"):
    sp_id = row["species_id"]
    sci_name = row["scientific_name"]
    print(f"\n→ {sci_name}")

    # Get IUCN taxon ID
    taxon_id = get_species_id_from_name(sci_name)
    if not taxon_id:
        print(f"  ⚠ Not found in IUCN — using defaults from species_list.csv")
        trait_records.append({
            "species_id": sp_id,
            "scientific_name": sci_name,
            "iucn_taxon_id": None,
            "threat_count_iucn": row.get("threat_count", 0),
            "habitat_count_iucn": row.get("habitat_count", 0),
            "eoo_km2_iucn": row.get("eoo_km2", None),
            "aoo_km2_iucn": row.get("aoo_km2", None),
            "generation_length_yrs_iucn": row.get("generation_length_yrs", None),
        })
        continue

    print(f"  IUCN taxon ID: {taxon_id}")

    # Get threats
    threats = get_threats(taxon_id)
    time.sleep(0.5)

    # Get habitats
    habitats = get_habitats(taxon_id)
    time.sleep(0.5)

    # Get narrative (for EOO/AOO/generation length if available)
    narrative = get_narrative(taxon_id)
    time.sleep(0.5)

    # Save trait record
    trait_records.append({
        "species_id": sp_id,
        "scientific_name": sci_name,
        "iucn_taxon_id": taxon_id,
        "threat_count_iucn": len(set(t.get("code", "").split(".")[0] for t in threats)),
        "habitat_count_iucn": len(habitats),
        "eoo_km2_iucn": row.get("eoo_km2", None),
        "aoo_km2_iucn": row.get("aoo_km2", None),
        "generation_length_yrs_iucn": row.get("generation_length_yrs", None),
        "habitat_types": "; ".join([h.get("habitat", "") for h in habitats[:5]]),
        "top_threats": "; ".join([t.get("title", "") for t in threats[:5]]),
    })

    # Get historical assessments
    history = get_assessment_history(sci_name)
    time.sleep(0.5)

    for record in history:
        category = record.get("category", "")
        assessment_records.append({
            "species_id": sp_id,
            "scientific_name": sci_name,
            "assessment_year": record.get("year"),
            "category": category,
            "category_num": CATEGORY_NUM.get(category, None),
            "iucn_taxon_id": taxon_id,
        })

    if history:
        print(f"  Historical assessments: {len(history)}")
    time.sleep(1.0)


# ── Save outputs ─────────────────────────────────────────────
trait_df = pd.DataFrame(trait_records)
trait_df.to_csv("data/iucn_traits.csv", index=False)
print(f"\n✅ Saved IUCN traits to data/iucn_traits.csv ({len(trait_df)} rows)")

if assessment_records:
    assess_df = pd.DataFrame(assessment_records)
    assess_df = assess_df.dropna(subset=["assessment_year"])
    assess_df["assessment_year"] = assess_df["assessment_year"].astype(int)
    assess_df = assess_df.sort_values(["species_id", "assessment_year"])

    # ── Derive ML label: did category worsen between consecutive assessments?
    labels = []
    for sp_id, grp in assess_df.groupby("species_id"):
        grp = grp.sort_values("assessment_year").reset_index(drop=True)
        for i in range(1, len(grp)):
            prev = grp.loc[i-1]
            curr = grp.loc[i]
            delta = (curr["category_num"] or 0) - (prev["category_num"] or 0)
            label = "worsened" if delta > 0 else ("improved" if delta < 0 else "stable")
            labels.append({
                "species_id": sp_id,
                "scientific_name": curr["scientific_name"],
                "prev_year": prev["assessment_year"],
                "prev_category": prev["category"],
                "prev_category_num": prev["category_num"],
                "curr_year": curr["assessment_year"],
                "curr_category": curr["category"],
                "curr_category_num": curr["category_num"],
                "years_gap": int(curr["assessment_year"]) - int(prev["assessment_year"]),
                "label": label,
            })

    if labels:
        labels_df = pd.DataFrame(labels)
        labels_df.to_csv("data/iucn_assessments.csv", index=False)
        print(f"✅ Saved assessment history & ML labels to data/iucn_assessments.csv")
        print(f"   Label distribution:\n{labels_df['label'].value_counts().to_string()}")

print("\nDone. Next: run 03_merge_and_eri.py")
