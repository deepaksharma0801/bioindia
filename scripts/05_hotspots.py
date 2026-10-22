"""
SCRIPT 05 — Spatial Hotspot Detection & Protection Gap Analysis
===============================================================
Prerequisites:
    pip install pandas numpy geopandas scipy esda libpysal shapely matplotlib

Protected Area data:
    Download India's PA shapefile from:
    https://www.protectedplanet.net/country/IN
    → Click "Download" → select "GeoJSON" format
    → Save as: data/india_protected_areas.geojson

Inputs:
    data/occurrences_raw.csv
    data/species_eri.json
    data/india_protected_areas.geojson   (manual download required)

Outputs:
    data/hotspots.geojson     (top 9 hotspot regions for dashboard)
    data/gap_table.csv        (unprotected hotspot regions for report)
    outputs/hotspot_map.png   (Figure for paper)

Run: python 05_hotspots.py
"""

import pandas as pd
import numpy as np
import json
import os
import warnings
warnings.filterwarnings("ignore")

import geopandas as gpd
from shapely.geometry import Point, box
from scipy.stats import gaussian_kde
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

os.makedirs("data", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ── Load occurrence data ─────────────────────────────────────
raw_df = pd.read_csv("data/occurrences_raw.csv")
print(f"Loaded {len(raw_df)} raw occurrences")

# ── Load ERI scores to filter high-risk species ──────────────
with open("data/species_eri.json") as f:
    eri_list = json.load(f)
eri_df = pd.DataFrame(eri_list)
high_risk_ids = set(eri_df[eri_df["eri_score"] >= eri_df["eri_score"].quantile(0.75)]["species_id"])
print(f"High-risk species (top quartile ERI): {len(high_risk_ids)}")

# Filter to high-risk species occurrences only
hr_occ = raw_df[raw_df["species_id"].isin(high_risk_ids)].dropna(subset=["latitude","longitude"])
print(f"High-risk occurrences: {len(hr_occ)}")

# ── Grid-based richness map ──────────────────────────────────
# India bounding box
LAT_MIN, LAT_MAX = 6.5, 37.5
LON_MIN, LON_MAX = 68.0, 98.0
CELL_SIZE = 0.5  # degrees (~55 km)

lat_bins = np.arange(LAT_MIN, LAT_MAX, CELL_SIZE)
lon_bins = np.arange(LON_MIN, LON_MAX, CELL_SIZE)

hr_occ["lat_bin"] = pd.cut(hr_occ["latitude"],  bins=lat_bins, labels=lat_bins[:-1])
hr_occ["lon_bin"] = pd.cut(hr_occ["longitude"], bins=lon_bins, labels=lon_bins[:-1])

hr_occ["lat_bin"] = hr_occ["lat_bin"].astype(float)
hr_occ["lon_bin"] = hr_occ["lon_bin"].astype(float)

# Species richness per grid cell (unique species count)
grid_richness = (
    hr_occ.dropna(subset=["lat_bin","lon_bin"])
    .groupby(["lat_bin","lon_bin"])["species_id"]
    .nunique()
    .reset_index(name="species_richness")
)

# Record density per grid cell
grid_density = (
    hr_occ.dropna(subset=["lat_bin","lon_bin"])
    .groupby(["lat_bin","lon_bin"])
    .size()
    .reset_index(name="record_count")
)

grid = grid_richness.merge(grid_density, on=["lat_bin","lon_bin"], how="outer").fillna(0)

# Combined score: richness × log(density+1)
grid["hotspot_score"] = grid["species_richness"] * np.log1p(grid["record_count"])
grid["hotspot_score_norm"] = 100 * grid["hotspot_score"] / grid["hotspot_score"].max()

print(f"\nGrid cells with data: {len(grid)}")
print(f"Top 5 hotspot cells:\n{grid.nlargest(5,'hotspot_score')[['lat_bin','lon_bin','species_richness','hotspot_score_norm']].to_string(index=False)}")


# ── Protected Area overlay ───────────────────────────────────
PA_FILE = "data/india_protected_areas.geojson"
has_pa_data = os.path.exists(PA_FILE)

if has_pa_data:
    print("\nLoading Protected Area boundaries...")
    pa_gdf = gpd.read_file(PA_FILE)
    pa_gdf = pa_gdf.to_crs(epsg=4326)

    # For each hotspot grid cell, calculate % PA coverage
    grid_gdf = gpd.GeoDataFrame(
        grid,
        geometry=[box(row.lon_bin, row.lat_bin,
                      row.lon_bin + CELL_SIZE, row.lat_bin + CELL_SIZE)
                  for _, row in grid.iterrows()],
        crs="EPSG:4326"
    )

    # Project to area-preserving CRS for area calculations
    grid_proj = grid_gdf.to_crs(epsg=32644)  # UTM Zone 44N (central India)
    pa_proj   = pa_gdf.to_crs(epsg=32644)

    pa_coverage = []
    for idx, cell in grid_proj.iterrows():
        cell_area = cell.geometry.area
        intersection = pa_proj.intersection(cell.geometry).area.sum()
        pct = min(100.0, 100 * intersection / cell_area) if cell_area > 0 else 0
        pa_coverage.append(round(pct, 1))

    grid["pa_coverage_pct"] = pa_coverage
else:
    print(f"\n⚠ Protected Area GeoJSON not found at {PA_FILE}")
    print("  Download from https://www.protectedplanet.net/country/IN")
    print("  Proceeding without PA gap analysis...")
    grid["pa_coverage_pct"] = np.nan


# ── Classify hotspot status ──────────────────────────────────
def classify_cell(row):
    if row["hotspot_score_norm"] < 30:
        return "low_risk"
    if pd.isna(row["pa_coverage_pct"]):
        return "hotspot_unknown_pa"
    if row["pa_coverage_pct"] >= 20:
        return "protected_hotspot"
    return "gap_hotspot"

grid["gap_status"] = grid.apply(classify_cell, axis=1)


# ── Select top 9 hotspot cells for dashboard ─────────────────
# Name each hotspot cell by approximate region
REGION_NAMES = {
    # (lat_floor, lon_floor): "Region Name"
    (8.5, 76.5): "Western Ghats South (Kerala–TN)",
    (11.5, 75.5): "Western Ghats Central (Karnataka)",
    (18.5, 79.0): "Telangana–Chhattisgarh Border",
    (22.5, 82.0): "Central Indian Highlands (MP–CG)",
    (26.5, 82.5): "Terai-Gangetic Floodplain (UP)",
    (26.0, 90.0): "Brahmaputra Floodplain (Assam)",
    (27.0, 95.0): "Eastern Himalayan Foothills (Arunachal)",
    (13.0, 79.5): "Eastern Ghats (AP–TN)",
    (24.0, 70.0): "Rann of Kutch (Gujarat)",
    (20.0, 85.0): "Odisha Coast–Chilika",
    (12.0, 77.0): "Nilgiri Biosphere",
    (29.5, 79.5): "Uttarakhand Himalayas",
}

def lookup_region(lat, lon):
    best = None
    best_dist = float("inf")
    lat_f = round(lat / CELL_SIZE) * CELL_SIZE
    lon_f = round(lon / CELL_SIZE) * CELL_SIZE
    for (rl, rlon), name in REGION_NAMES.items():
        d = abs(lat_f - rl) + abs(lon_f - rlon)
        if d < best_dist:
            best_dist = d
            best = name
    return best if best_dist < 3 else f"Lat {lat:.1f}°N, Lon {lon:.1f}°E"

top9 = grid.nlargest(9, "hotspot_score").reset_index(drop=True)
top9["rank"] = top9.index + 1
top9["region_name"] = top9.apply(lambda r: lookup_region(r["lat_bin"], r["lon_bin"]), axis=1)

print(f"\nTop 9 Hotspots:")
print(top9[["rank","region_name","species_richness","hotspot_score_norm","pa_coverage_pct","gap_status"]].to_string(index=False))


# ── Save hotspots.geojson for dashboard ──────────────────────
features = []
for _, row in top9.iterrows():
    lat, lon = row["lat_bin"], row["lon_bin"]
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon, lat], [lon+CELL_SIZE, lat],
                [lon+CELL_SIZE, lat+CELL_SIZE], [lon, lat+CELL_SIZE], [lon, lat]
            ]]
        },
        "properties": {
            "rank": int(row["rank"]),
            "region_name": row["region_name"],
            "species_richness": int(row["species_richness"]),
            "record_count": int(row["record_count"]),
            "hotspot_score": round(float(row["hotspot_score_norm"]), 1),
            "pa_coverage_pct": float(row["pa_coverage_pct"]) if not pd.isna(row["pa_coverage_pct"]) else None,
            "gap_status": row["gap_status"],
            "centroid_lat": round(lat + CELL_SIZE/2, 3),
            "centroid_lon": round(lon + CELL_SIZE/2, 3),
        }
    })

geojson = {"type": "FeatureCollection", "features": features}
with open("data/hotspots.geojson", "w") as f:
    json.dump(geojson, f, indent=2)
print(f"\n✅ Saved hotspots.geojson")


# ── Save gap table for report ─────────────────────────────────
gap_df = grid[grid["gap_status"] == "gap_hotspot"].nlargest(20, "hotspot_score")
gap_df["region_name"] = gap_df.apply(lambda r: lookup_region(r["lat_bin"], r["lon_bin"]), axis=1)
gap_df.to_csv("data/gap_table.csv", index=False)
print(f"✅ Saved gap_table.csv ({len(gap_df)} gap hotspot cells)")


# ── Figure: Hotspot Map ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 12))
scatter = ax.scatter(
    grid["lon_bin"] + CELL_SIZE/2,
    grid["lat_bin"] + CELL_SIZE/2,
    c=grid["hotspot_score_norm"],
    cmap="YlOrRd", s=30, alpha=0.7
)
plt.colorbar(scatter, ax=ax, label="Hotspot Score (normalized, 0-100)")

# Mark top 9
for _, row in top9.iterrows():
    ax.plot(row["lon_bin"]+CELL_SIZE/2, row["lat_bin"]+CELL_SIZE/2,
            "r*", markersize=14, zorder=5)
    ax.annotate(
        f"#{int(row['rank'])}",
        xy=(row["lon_bin"]+CELL_SIZE/2, row["lat_bin"]+CELL_SIZE/2),
        xytext=(5, 5), textcoords="offset points", fontsize=7, color="darkred"
    )

ax.set_xlim(LON_MIN, LON_MAX)
ax.set_ylim(LAT_MIN, LAT_MAX)
ax.set_xlabel("Longitude (°E)")
ax.set_ylabel("Latitude (°N)")
ax.set_title("High-Risk Species Richness Hotspots — India\n(★ = Top 9 Hotspot Cells)")
ax.set_aspect("equal")
plt.tight_layout()
plt.savefig("outputs/hotspot_map.png", dpi=150)
plt.close()
print("✅ Saved hotspot_map.png")

print("\nDone. Next: run 06_trajectory_ml.py")
