# BioIndia — Data Pipeline Scripts
## Setup & Execution Guide

### Step 1: Install Python dependencies
```bash
pip install requests pandas numpy geopandas scipy scikit-learn imbalanced-learn xgboost matplotlib seaborn tqdm shapely
```

### Step 2: Create project folders
```
BioIndia/
  scripts/        ← put all these .py files here
  data/           ← auto-created by scripts
  outputs/        ← auto-created by scripts (figures)
  index.html      ← your existing dashboard
```

### Step 3: Get your IUCN API token
1. Go to https://api.iucnredlist.org/
2. Click "Request a token"
3. Fill in: your name, institution (VIT), purpose (academic research on Indian biodiversity)
4. Token arrives by email in 1–2 days
5. Open `02_iucn_data.py` and paste token in `IUCN_TOKEN = "YOUR_TOKEN_HERE"`

### Step 4: Download Protected Area boundaries
1. Go to https://www.protectedplanet.net/country/IN
2. Click Download → GeoJSON
3. Save as `data/india_protected_areas.geojson`

### Step 5: Run scripts IN ORDER
```bash
cd scripts/
python 00_species_list.py       # builds species list (no internet needed)
python 01_gbif_occurrences.py   # pulls GBIF data (~30-60 min)
python 02_iucn_data.py          # pulls IUCN traits & history (~20 min, needs token)
python 03_merge_and_eri.py      # computes ERI via PCA
python 04_trends_and_state_db.py  # builds trend arrays + state_species.json
python 05_hotspots.py           # spatial hotspot detection
python 06_trajectory_ml.py      # ML watchlist prediction
```

### Step 6: Wire into dashboard
Copy the `data/` folder output next to your `index.html`, then follow
the HTML wiring instructions in the Final Plan document.

---

## Output Files Summary

| File | Used in Dashboard | Used in Paper |
|------|------------------|---------------|
| data/state_species.json | ✅ Replaces STATE_DB | — |
| data/species_eri.json | ✅ ERI badges | ✅ Table 1 |
| data/hotspots.geojson | ✅ Hotspot grid | ✅ Figure 2 |
| data/species_trends.json | ✅ Trend charts | — |
| data/watchlist.json | ✅ Watchlist section | ✅ Table 2 |
| data/gap_table.csv | — | ✅ Table 3 |
| outputs/pca_biplot.png | — | ✅ Figure 1 |
| outputs/hotspot_map.png | — | ✅ Figure 2 |
| outputs/feature_importance.png | — | ✅ Figure 3 |
| outputs/confusion_matrix.png | — | ✅ Supplementary |

## Species Covered: 60 species
- Mammals: 24 (including EX Cheetah, CR Hangul, EN Dhole, Tiger, Elephant)
- Birds: 16 (including CR Great Indian Bustard, CR 3 vulture species, CR Pink-headed Duck)
- Reptiles: 6 (including CR Gharial, VU Sea Turtles)
- Amphibians: 3 (including EN Purple Frog — described 2003)
- Fish: 3 (including CR Ganges Shark, CR Pondicherry Shark)
- Plants: 10 (including CR Agarwood, CR Assam Catkin Yew, EN Blue Vanda, EN Pitcher Plant)
