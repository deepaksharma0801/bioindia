# BioIndia - India Biodiversity Intelligence Platform

MSc project: *AI-Driven Biodiversity Intelligence Platform for India: Extinction Risk Assessment,
Spatio-Temporal Biodiversity Analysis, Conservation Prioritization, and Ecological Cascade Simulation.*
The brief and its 24 development phases are in `ste project roadmap.docx`; methods, every quality rule
and all known limitations are in [docs/METHODS.md](docs/METHODS.md).

**Scope:** 188 India-native species with IUCN Red List assessments (mammals, birds, reptiles, amphibians,
fishes, plants and invertebrates), including five flagships (tiger, Asian elephant, Indian rhinoceros,
sloth bear, mugger crocodile). 173 of them have GBIF records in India; 1,398,890 quality-controlled
occurrences are loaded into PostGIS.

The platform separates, everywhere, **observed data** (GBIF records, protected areas, climate, land use),
**official assessments** (IUCN), **derived metrics**, **model predictions** (labelled *MODEL PREDICTION*),
**scenario simulations** (labelled *SCENARIO SIMULATION*) and **experimental indices** (labelled
*EXPERIMENTAL RESEARCH METRIC*).

## Architecture

| Part | Where | Notes |
|---|---|---|
| Dashboard | `BioIndia_v3_Complete.html`, `bioindia-phase2.js` (states, hotspots), `bioindia-phase3.js` (map), `bioindia-phase5.js` (live AI, network, climate, reports) | Static HTML/JS + Leaflet. Reads the API; falls back to labelled demo content if the API is down |
| API | `backend/app/` | FastAPI; routers in `routers/`, logic in `services/`; schema as Alembic migrations in `backend/migrations/` |
| Database | PostGIS 3.4 (Docker) | `species`, `occurrences`, `conservation_assessments`, `protected_areas`, `analytics_grid_cells`, `species_interactions`, `model_registry`, `species_risk_predictions`, `land_use_cells`, `species_land_pressure` |
| Pipeline | `scripts/phase*.py`, run in order by `scripts/run_pipeline.py` | Each step writes a report to `data/analytics/` |
| Data and models | `data/`, `models/` | Not in git (size and licences) |

## Setup

Python 3.12+ (results produced with 3.14.3 on Windows 11) and Docker Desktop (WSL 2 on Windows). About 12 GB of disk.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements-pipeline.txt
```

```bash
docker compose up -d postgis
```

`requirements-lock.txt` pins the exact package versions behind the reported results. Copy `env.example`
to `.env` only to change credentials; the defaults match `docker-compose.yml`.

## Data sources (place in `data/raw/` unless noted)

| Source | Location | Licence / terms |
|---|---|---|
| GBIF occurrences, download `0006542-261023074918325` | `data/raw/gbif/<key>.zip` (request in `data/raw/gbif/gbif_download_request*.json`) | Mixed CC0 / CC BY / CC BY-NC; cite GBIF.org (2026) https://doi.org/10.15468/dl.dvgq2s |
| IUCN Red List export (retrieved 2026-10-21) | the long-named UUID folders in the project root | IUCN terms: non-commercial research use, no redistribution |
| OpenStreetMap India | `data/raw/protected_areas/osm/india-latest.osm.pbf` (Geofabrik) | ODbL 1.0 |
| WDPA India (Oct 2026) | `data/raw/protected_areas/WDPA_WDOECM_Oct2026_Public_IND_shp.zip` | Non-commercial; no redistribution |
| WorldClim 2.1, 10′ | `data/raw/worldclim/wc2.1_10m_bio.zip`, `wc2.1_10m_elev.zip` | Cite Fick & Hijmans (2017) |
| Hansen Global Forest Change 2000–2024 v1.12 | `data/raw/landuse/hansen/` (11 tiles × 3 layers, 2.3 GB) | CC BY 4.0; cite Hansen et al. (2013) |
| GHSL R2023A built-up and population, 2020, 30″ | `data/raw/landuse/ghsl/built.zip`, `pop.zip` (0.7 GB) | CC BY 4.0, European Commission JRC |
| geoBoundaries India ADM1 | `data/raw/boundaries/geoBoundaries-IND-ADM1.geojson` | CC BY 2.5 IN |
| Natural Earth countries | `data/raw/boundaries/ne_10m_admin_0_countries.zip` | Public domain |
| GBIF facet summaries, GloBI interactions | fetched by `phase14_fetch_gbif_summaries.py` and `phase16_fetch_globi.py` | GBIF terms; GloBI per-source licences |

`bash scripts/phase10_download_landuse.sh` fetches the Hansen and GHSL files. The GBIF download is
requested once under your GBIF account with the saved request JSON.

## Pipeline

```bash
.venv/Scripts/python scripts/run_pipeline.py
```

`--list` shows the 20 steps; `--from phase9` resumes from a step. Steps in order: schema, state
boundaries, zoo outlines, species list, GBIF screen and sample, PostGIS load, IUCN import, protected
areas (WDPA, OSM), climate, land use, grid metrics, GBIF summaries, GloBI interactions, risk model,
dashboard fallback files.

## Running

```bash
docker compose --profile app up -d --build
```

This starts PostGIS, the API and the dashboard behind nginx at http://localhost:8080 (API docs at
http://localhost:8080/docs). The API container applies migrations on start and reads `data/` read-only;
all ports bind to localhost only.

For development, run the two servers from `.claude/launch.json` instead:

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

```bash
.venv/Scripts/python -m http.server 5500
```

and open http://127.0.0.1:5500/BioIndia_v3_Complete.html (set `DATABASE_URL` for the API).

## API (prefix `/api/v1`, interactive docs at `/docs`)

| Area | Routes |
|---|---|
| Species | `/species`, `/species/search`, `/species/state-profiles`, `/species/occurrences`, `/species/{id}` and `/{id}/occurrences`, `/trend`, `/observation-time-series`, `/intelligence`, `/conservation`, `/environment`, `/land-pressure`, `/protection` |
| Map / GIS | `/map/occurrences` (species, bbox, state, years, IUCN category, `within_10_km_only`), `/map/hotspots`, `/gis/state-boundaries` |
| Analytics | `/analytics/biodiversity-trends`, `/biodiversity-concentration`, `/hotspots`, `/conservation-priority`, `/threatened-species` |
| Land use | `/land-use/states`, `/land-use/states/{state}` |
| Network | `/network/species/{id}`, `/network/ecosystem/{region}` |
| Model | `/prediction/ranking`, `/prediction/species/{id}`, `/prediction/species/{id}/explanation`, `/model-info`, `/model-performance` |
| Scenarios | `POST /simulation/extinction-cascade` |
| Indices | `/indices/ibvci`, `/indices/ibvci/{id}`, `/indices/cipi` (custom `weights=name:value,...`) |
| Reports | `POST /reports/regional` (JSON with every figure's evidence, plus Markdown) |

## Testing

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

```bash
.venv/Scripts/python -m pytest -q scripts/tests
```

Backend tests run against the loaded database and skip themselves if it is unreachable or a stage
(risk model, land-use grid) has not been built; a separate group checks the 503 responses without a
database. Script tests are unit tests of the quality rules and need no data.

## Key limitations (full list in [docs/METHODS.md](docs/METHODS.md))

- Occurrence records measure recording effort, not abundance or population trends.
- The IUCN export does not include the five flagship species, so their categories are source-reported and marked unverified.
- The risk model is trained on 168 species (27 threatened); its PR-AUC of 0.48 ± 0.14 is well above chance (0.16) but uncertain. Its predictions are not IUCN assessments.
- "Hotspots" are record concentration zones, not recognised biodiversity hotspots.
- Hansen "forest" is tree cover (including plantations); loss includes harvest and natural disturbance.
- Cascade outputs are scenarios over documented interactions, which are incomplete and biased towards well-studied taxa.
