# BioIndia - India Biodiversity Intelligence Platform

MSc project: an India-focused biodiversity decision-support platform (extinction risk, spatio-temporal
analysis, conservation prioritization). The full brief and its 24 development phases are in
`ste project roadmap.docx`.

**Current scope:** five tracked species — Tiger, Asian Elephant, Indian Rhinoceros, Sloth Bear and
Mugger Crocodile — with real GBIF occurrences, protected areas and baseline climate in PostGIS.

## Architecture

| Part | Where | Notes |
|---|---|---|
| Dashboard | `BioIndia_v3_Complete.html`, `bioindia-phase2.js`, `bioindia-phase3.js` | Static HTML/JS + Leaflet; reads the API, falls back to `data/processed/` |
| API | `backend/app/` | FastAPI; routers in `routers/`, logic in `services/`, schema in `database/schema.sql` |
| Database | PostGIS 3.4 (Docker) | Tables: `species`, `occurrences`, `protected_areas`, `conservation_assessments`, `occurrence_land_pressure`, `analytics_grid_cells` |
| Pipelines | `scripts/phase*.py` | Reproducible import, cleaning and analytics steps |
| Data | `data/raw`, `data/processed`, `data/analytics` | Not in git (size and licences) |

## Prerequisites

- Python 3.12+ (developed on 3.14) and Docker Desktop (with WSL 2 on Windows)
- About 4 GB of disk for data

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt pandas numpy geopandas pyogrio shapely rasterio pytest httpx
docker compose up -d postgis
```

Copy `env.example` to `.env` if you need other credentials; the defaults match `docker-compose.yml`.

## Data sources (download into `data/raw/`)

| Source | File / location | Licence |
|---|---|---|
| GBIF occurrences | `data/raw/gbif/<key>.zip` — request in `data/raw/gbif/gbif_download_request.json` | CC BY-NC 4.0 (combined); cite https://doi.org/10.15468/dl.5vweks |
| OpenStreetMap protected areas | `data/raw/protected_areas/osm/india-latest.osm.pbf` (Geofabrik) | ODbL 1.0 |
| WDPA India | `data/raw/protected_areas/WDPA_WDOECM_Oct2026_Public_IND_shp.zip` (protectedplanet.net) | Non-commercial; no redistribution |
| WorldClim 2.1 (10′) | `data/raw/worldclim/wc2.1_10m_bio.zip`, `wc2.1_10m_elev.zip` | Academic/non-commercial; cite Fick & Hijmans (2017) |
| State boundaries | `data/raw/boundaries/geoBoundaries-IND-ADM1.geojson` | CC BY 2.5 IN |
| Neighbour countries | `data/raw/boundaries/ne_10m_admin_0_countries.zip` (Natural Earth) | Public domain |
| IUCN Red List export | the four long-named folders in the project root | Research use only; no redistribution |

## Pipeline (run in order, from the project root)

```bash
.venv/Scripts/python scripts/prepare_state_boundaries.py         # 36 states/UTs
.venv/Scripts/python scripts/phase4_prepare_postgis_inputs.py    # GBIF quality screen + exclusion log
.venv/Scripts/python scripts/phase4_load_postgis.py              # species + occurrences
.venv/Scripts/python scripts/phase11_load_wdpa.py                # WDPA forest/other layers (also --dry-run)
.venv/Scripts/python scripts/phase11_compare_osm_wdpa.py         # OSM extract, India filter, comparison
.venv/Scripts/python scripts/phase11_load_osm.py                 # OSM wildlife + tiger-reserve layers
.venv/Scripts/python scripts/phase9_sample_worldclim.py          # climate profiles
.venv/Scripts/python scripts/phase13_build_grid_metrics.py       # grid-cell analytics table
.venv/Scripts/python scripts/phase5_export_dashboard_data.py     # dashboard fallback files
```

Each step writes a report to `data/analytics/`. Scripts `00`–`06`, `phase1_*`, `phase3_*`,
`phase4_build_dashboard_outputs.py` and `phase11_load_protected_areas.py` are the earlier prototype
pipeline; they need source files that are not available and are kept for reference only.

## Running

The launch configurations are in `.claude/launch.json`:

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

```bash
.venv/Scripts/python -m http.server 5500
```

Set `DATABASE_URL=postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia` for the API. Then open
http://127.0.0.1:5500/BioIndia_v3_Complete.html; API docs are at http://127.0.0.1:8000/docs.

## API (main routes, prefix `/api/v1`)

- Species: `/species`, `/species/search`, `/species/{id}`, `/species/{id}/occurrences|trend|intelligence|conservation|environment|protection|observation-time-series`, `/species/state-profiles`
- Map: `/map/occurrences` (filters: species, bbox, state, years, IUCN category, `within_10_km_only`), `/map/hotspots` — also under `/gis/`
- Analytics: `/analytics/biodiversity-trends`, `/analytics/biodiversity-concentration`, `/analytics/hotspots`, `/analytics/conservation-priority`, `/analytics/threatened-species`

## Testing

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

```bash
.venv/Scripts/python -m pytest -q scripts/tests
```

Backend tests run against the loaded PostGIS database and skip if it is unreachable; a separate group
checks the 503 responses without a database.

## Scientific limitations

- **Occurrence records are not abundance.** Counts reflect where and when people record; there is no survey-effort correction.
- **Most coordinates are obscured.** ~89% of records have > 10 km uncertainty (threatened species are blurred by publishers). Protection and climate figures use only records within 10 km and report what was left out; rhino has only 9 such records.
- **Precise elephant and sloth bear records come almost entirely from Tamil Nadu surveys**, so their figures describe those areas.
- **IUCN categories are source-reported**, not verified; the IUCN export in this folder does not cover the five species.
- **OSM protected areas are community-mapped**, not an official list. 18 tiger reserves also count as wildlife protected areas (17 by name, Anamalai by a documented manual list); their outlines may include buffer zones.
- **Concentration zones are data-derived**, not officially recognised biodiversity hotspots. Five species are too few for meaningful richness or priority analysis at national scale.
- **Not yet built:** habitat/land-use pressure, IUCN import for these species, extinction-risk model, explainability, interaction network, cascade simulator, research indices and reports (roadmap phases 8, 10, 14–20).
