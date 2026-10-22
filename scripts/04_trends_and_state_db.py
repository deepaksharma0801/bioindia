"""
SCRIPT 04 — Real Trend Arrays & State Species JSON
====================================================
Builds the two JSON files needed to replace hardcoded data in the
existing BioIndia HTML dashboard.

Prerequisites:
    pip install pandas numpy

Inputs:
    data/species_master.csv
    data/occurrences_by_year.csv
    data/occurrences_by_state.csv

Outputs:
    data/species_trends.json        (26-year trend arrays per species)
    data/state_species.json         (drop-in replacement for STATE_DB)

Run: python 04_trends_and_state_db.py
"""

import pandas as pd
import numpy as np
import json
import os

os.makedirs("data", exist_ok=True)

YEAR_START = 1999
YEAR_END = 2024
YEARS = list(range(YEAR_START, YEAR_END + 1))  # 26 years

# ── Load data ────────────────────────────────────────────────
master_df   = pd.read_csv("data/species_master.csv")
year_df     = pd.read_csv("data/occurrences_by_year.csv") if os.path.exists("data/occurrences_by_year.csv") else pd.DataFrame()
state_df    = pd.read_csv("data/occurrences_by_state.csv") if os.path.exists("data/occurrences_by_state.csv") else pd.DataFrame()

print(f"Master species: {len(master_df)}")


def normalize_to_100(arr):
    """Normalize an array of counts to 0-100 scale."""
    arr = np.array(arr, dtype=float)
    if arr.max() == 0:
        return [0] * len(arr)
    normed = 100 * arr / arr.max()
    return [round(v, 1) for v in normed]


def confidence_scores(arr):
    """1 = good data, 0 = no data for that year."""
    arr = np.array(arr, dtype=float)
    return [1 if v > 0 else 0 for v in arr]


# ── Build trend arrays ───────────────────────────────────────
trend_data = {}

for _, row in master_df.iterrows():
    sp_id = row["species_id"]
    sci_name = row["scientific_name"]

    if not year_df.empty:
        sp_years = year_df[year_df["species_id"] == sp_id]
        if not sp_years.empty:
            raw_counts = []
            for yr in YEARS:
                col = str(yr)
                raw_counts.append(sp_years[col].values[0] if col in sp_years.columns else 0)
            trend = normalize_to_100(raw_counts)
            confidence = confidence_scores(raw_counts)
        else:
            # No GBIF data — use flat trend (no information)
            trend = [0] * len(YEARS)
            confidence = [0] * len(YEARS)
    else:
        trend = [0] * len(YEARS)
        confidence = [0] * len(YEARS)

    trend_data[sp_id] = {
        "scientific_name": sci_name,
        "trend": trend,
        "confidence": confidence,
        "years": YEARS,
        "note": "Normalized GBIF occurrence record counts per year (not population counts)"
    }

with open("data/species_trends.json", "w") as f:
    json.dump(trend_data, f, indent=2)
print(f"✅ Saved trend arrays to data/species_trends.json")


# ── Build STATE_DB replacement ───────────────────────────────
# All 36 Indian states + UTs that your HTML currently uses as keys
ALL_STATES = [
    "Andaman & Nicobar", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
    "Bihar", "Chandigarh", "Chhattisgarh", "Dadra & Nagar Haveli",
    "Daman & Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu & Kashmir", "Jharkhand", "Karnataka",
    "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha",
    "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal"
]

# Build a lookup: species_id -> master row
species_lookup = master_df.set_index("species_id").to_dict(orient="index")

# Build a lookup: (species_id, state) -> obs_count
obs_lookup = {}
if not state_df.empty:
    for _, row in state_df.iterrows():
        obs_lookup[(row["species_id"], row["state"])] = int(row["obs_count"])

state_db = {}

for state in ALL_STATES:
    species_in_state = []

    for sp_id, sp_data in species_lookup.items():
        obs = obs_lookup.get((sp_id, state), 0)

        # Only include species with actual observations in this state,
        # or if it's one of the original 5 core species (always show them)
        CORE_SPECIES = {"SP012", "SP013", "SP014", "SP016", "SP032"}
        if obs == 0 and sp_id not in CORE_SPECIES:
            continue

        trend = trend_data.get(sp_id, {}).get("trend", [0]*26)

        species_in_state.append({
            "e": str(sp_data.get("emoji", "🦎")),
            "n": str(sp_data.get("common_name", "")),
            "s": str(sp_data.get("scientific_name", "")),
            "st": str(sp_data.get("iucn_status_code", "lc")),
            "h": str(sp_data.get("habitat_count", "—")),
            "obs": obs,
            "trend": trend,
            "desc": str(sp_data.get("description", "")),
            "eri": round(float(sp_data.get("eri_score", 0) or 0), 1),
            "taxonomic_group": str(sp_data.get("taxonomic_group", "")),
        })

    # Sort by obs_count descending (most-observed first, matching original behavior)
    species_in_state.sort(key=lambda x: x["obs"], reverse=True)

    # Fallback: if no species found for a state, include the 5 core species with obs=0
    if not species_in_state:
        for sp_id in CORE_SPECIES:
            if sp_id not in species_lookup:
                continue
            sp_data = species_lookup[sp_id]
            trend = trend_data.get(sp_id, {}).get("trend", [0]*26)
            species_in_state.append({
                "e": str(sp_data.get("emoji", "🦎")),
                "n": str(sp_data.get("common_name", "")),
                "s": str(sp_data.get("scientific_name", "")),
                "st": str(sp_data.get("iucn_status_code", "lc")),
                "h": str(sp_data.get("habitat_count", "—")),
                "obs": 0,
                "trend": trend,
                "desc": str(sp_data.get("description", "")),
                "eri": 0.0,
                "taxonomic_group": str(sp_data.get("taxonomic_group", "")),
            })

    state_db[state] = species_in_state

with open("data/state_species.json", "w") as f:
    json.dump(state_db, f, indent=2)

# Summary
total_entries = sum(len(v) for v in state_db.values())
states_with_data = sum(1 for v in state_db.values() if any(e["obs"] > 0 for e in v))
print(f"✅ Saved state_species.json: {total_entries} state-species entries across {len(ALL_STATES)} states")
print(f"   States with real observation data: {states_with_data}/{len(ALL_STATES)}")

print("\nDone. Next: run 05_hotspots.py")
