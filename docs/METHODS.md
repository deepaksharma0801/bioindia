# BioIndia - methods, provenance and limitations

This document records how every dataset, metric, model and index in the platform is produced, with
the numbers from the run used for the thesis (data retrieved 21–27 October 2026). Each pipeline step
also writes a machine-readable report to `data/analytics/`; file names are given in brackets.

Terminology used throughout the platform:

| Label | Meaning |
|---|---|
| Observed data | GBIF records, protected-area outlines, climate and land-cover rasters, as published |
| Official assessment | an IUCN Red List category imported with provenance |
| Source-reported category | a category from the project reference list, not verified against an IUCN import |
| Derived metric | a transparent calculation over observed data (counts, shares, ranks) |
| MODEL PREDICTION | output of the extinction-vulnerability model; never an IUCN assessment |
| SCENARIO SIMULATION | output of the cascade simulator under stated assumptions; never a forecast |
| EXPERIMENTAL RESEARCH METRIC | IBVCI and CIPI; developed in this project, not established indices |

## 1. Species list (Phase 2) [`taxonomy_match_report.json`]

Candidates are India-native species with an assessment in the IUCN Red List export, chosen to cover
all major groups, plus five flagship species. Names are matched to the GBIF Backbone Taxonomy:
EXACT matches are accepted, FUZZY matches only with high confidence. Of 192 candidates, 188 were
accepted (183 exact, 5 fuzzy) and 4 sent to review (3 without a species-level match, 1 duplicate GBIF
concept). Where the GBIF backbone lacks a class (ray-finned fishes) or splits reptiles into orders,
the taxonomy is filled from the IUCN export.

## 2. Occurrence screening (Phases 3–4) [`screening_report.json`, `load_report.json`, `occurrence_exclusions.csv`]

Source: GBIF download `0006542-261023074918325` (https://doi.org/10.15468/dl.dvgq2s), 4,743,495 India
records for the 188 species.

**Record-level rules** (in `phase4_prepare_postgis_inputs.py`, every excluded record logged with its reason):

| Rule | Excluded |
|---|---|
| Missing coordinates | 10,259 |
| Missing date | 1,945 |
| GBIF geospatial issues (country mismatch, swapped or negated coordinates) | 239 |
| Date range spanning several years | 149 |
| Captive locality text (zoo, captive; plants: botanical garden) | 30 |
| Absence records | 16 |
| Living or fossil specimens | 26 |
| Non-native captive subspecies (Amur tiger) | 3 |
| Impossible date | 1 |

Captivity rules are group-aware: birds are only excluded on explicit captivity, because wild birds are
routinely recorded at zoos and gardens.

**Sampling.** Thirteen common birds have hundreds of thousands of records. To keep the database at
about 1.5 million records, each species is capped at 72,000: every record is kept with probability
cap / India record count, decided by a SHA-256 hash of the seed `bioindia-2026` and the GBIF ID. This
is reproducible and proportional across places and years. 3,233,259 records were sampled out.

**Coordinate uncertainty classes:** precise (≤ 1 km), moderate (≤ 10 km), coarse (> 10 km), unknown.
eBird records (dataset `4fa7b334-…`) without stated uncertainty and without a rounding flag are
treated as moderate (`uncertainty_assumed_ebird_protocol`), because eBird checklists are point or
short-traverse counts. Loaded records: precise 124,997 (8.9%), moderate 1,219,735 (87.2%), coarse
14,191 (1.0%), unknown 39,967 (2.9%).

**Spatial rules in PostGIS** (`phase4_load_postgis.py`):

| Rule | Excluded |
|---|---|
| Inside a mapped zoo (157 OSM zoo outlines; point-only zoos buffered 500 m; birds exempt) | 372 |
| More than 10 km from any Indian state | 358 |
| Duplicate upload: same species, named observer, ~11 m location and exact day (smallest uncertainty kept) | 97,948 |

Separate sightings sharing species, place and date are kept and flagged `shared_place_and_date`.
States are attributed by containment in geoBoundaries ADM1 polygons, else the nearest state within
10 km (coastal records). Result: 1,398,890 records for 173 species.

## 3. Conservation status (Phase 8) [`conservation_import_report.json`, `conservation_import_unmatched.csv`]

The IUCN export is matched by IUCN taxon ID. 183 of 254 rows were accepted; 7 accepted assessments
are for a subspecies or subpopulation and are labelled with `taxon_level`. **The export does not
contain the five flagship species**, so their categories come from the project reference list and are
shown as unverified everywhere.

## 4. Climate (Phase 9) [`climate_sampling_report.json`, `species_climate_profiles.json`]

WorldClim 2.1 (1970–2000 normals, 10′ ≈ 18 km) annual mean temperature, temperature seasonality,
annual precipitation, precipitation seasonality and elevation, sampled at records within 10 km
(1,344,705 samples). Per species: mean and 10th/90th percentiles (151 species). These are baseline
associations at observed locations, not climate-change exposure or suitability.

## 5. Land use, habitat pressure and forest change (Phase 10) [`land_use_report.json`]

- Hansen et al. Global Forest Change 2000–2024 v1.12 (30 m): tree cover in 2000 ≥ 30% canopy is
  "forest"; loss is counted only inside that forest, by year 2001–2024; gain is not subtracted.
- Fragmentation: share of 30 m forest pixels with a non-forest 4-neighbour (forest edge share).
- GHSL R2023A built-up surface and population, epoch 2020, 30″.
- All layers are aggregated to 0.05° cells (≈ 5.5 km; 118,686 cells). A cell belongs to the state
  containing its centre, else the state with the largest overlap; cells outside India are dropped.
- Checks: India land 3,285,405 km² (official 3,287,263 km²); population 1.41 billion; tree cover
  402,363 km² in 2000; loss 25,548 km² in 2001–2024 (Global Forest Watch reports about 23,300 km²
  for 2001–2023).
- Per species: mean conditions over the 0.05° cells it occupies with records within 10 km; each cell
  counts once so heavily recorded places do not dominate (151 species).

Limitations: tree cover includes plantations and orchards; loss includes plantation harvest, fire and
other natural disturbance; there are no land-cover classes (cropland, grassland, wetland); built-up
area and population are a single 2020 snapshot.

## 6. Protected areas (Phase 11) [`osm_protected_area_load_report.json`, `osm_wdpa_protected_area_comparison.json`]

The main wildlife layer is OpenStreetMap (Geofabrik extract of 22 October 2026): national parks,
wildlife sanctuaries and conservation/community reserves (659 features); 38 tiger reserves form a
separate layer. 18 tiger-reserve features whose names say National Park or Wildlife Sanctuary, plus
Anamalai (documented manual list, core is Indira Gandhi WLS and NP), also count as wildlife protected
areas. WDPA (October 2026) supplies the reserved-forest and other-designation layers. Features are
kept in India when their interior point and at least half their area are not on neighbouring land
(Natural Earth), with a documented list of border sanctuaries.

Protection figures per species use only records within 10 km and report how many records were left
out; a small-sample warning is shown below 30 records. Record share inside protected areas is not
habitat protection.

## 7. Time series (Phase 12)

Records per year and a normalised index (peak year = 100) per species and region, 2000 onward; the
current incomplete year is excluded. Changes in record counts reflect recording effort (eBird growth
after about 2015) at least as much as any change in populations.

## 8. Concentration and priority grid (Phase 13) [`grid_metrics_report.json`]

0.75° grid (592 cells with records). Each component is stored separately: records, observed species,
threatened species (verified category where imported, otherwise source-reported), recent records,
datasets, protected-area area shares by layer, and the Phase 10 land-use columns. Top cells are called
"record concentration zones", never biodiversity hotspots.

## 9. Extinction-vulnerability model (Phases 14–15) [`risk_model_report.json`]

- **Target:** IUCN CR/EN/VU (threatened) vs LC/NT, from verified assessments only; Data Deficient and
  unverified species are excluded from training and predicted as `unlabelled` (20 species).
- **Training set:** 168 species, 27 threatened (prevalence 0.161).
- **Features:** GBIF facet summaries for India (records, states, districts, concentration, years,
  recent-vs-earlier ratio, specimen share, datasets); range from all loaded records on a ~50 km grid and
  convex-hull extent; protected-area, climate-niche and land-use features from records within 10 km;
  taxonomic group indicators.
- **Leakage guard:** no feature describes location precision, because publishers deliberately blur
  threatened species' coordinates (an earlier version with such a feature was discarded). Range is
  computed on a coarse grid from all records for the same reason.
- **Evaluation:** repeated stratified 5-fold cross-validation (5 repeats); model chosen by mean PR-AUC.

| Model | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|
| Logistic regression | 0.401 ± 0.144 | 0.630 | 0.213 |
| **Random forest (selected)** | **0.481 ± 0.136** | **0.720** | **0.126** |
| XGBoost | 0.451 ± 0.122 | 0.708 | 0.141 |

Chance PR-AUC is 0.161. Predictions for training species are out-of-fold (from models that did not see
them). Calibration is imperfect: in the 0.2–0.4 and 0.4–0.6 bins the observed threatened shares are
0.16 and 0.31 against mean predictions of 0.29 and 0.48, so probabilities should be read as rankings.
The most important features (mean |SHAP|) are temperature niche breadth, fish group, tree cover in
occupied cells, precipitation niche breadth, elevation and recent forest loss. SHAP values explain the
model, not ecological causes.

## 10. Interaction network (Phase 16) [`interaction_load_report.json`]

GloBI interactions for all 188 species: 13,923 loaded, 13,469 documented. Inverse interaction types
are normalised so each link is counted once; `coOccursWith` and `adjacentTo` are stored as
co-occurrence associations and never counted as interactions; placeholder names (sp., spp., cf.,
aff.) and self-links are rejected. NetworkX metrics flag "potentially structurally important" species;
centrality is not evidence of keystone status. Records are global literature, not India-specific, and
heavily biased towards well-studied taxa (parasites of large mammals are over-represented).

## 11. Cascade simulator (Phase 17)

Only interaction types with a clear direction of dependence are used (e.g. eats, preysOn, hostOf,
hasParasite, symbiontOf); vague types are ignored. After removing a species, any taxon that has lost
at least a threshold share (default 50%) of its documented resources is marked as potentially
secondarily lost, and removal propagates step by step. Outputs report sensitivity at thresholds 0.25,
0.5 and 0.75 and flag taxa with a single documented resource as low confidence. Example: removing the
tiger gives 72 directly dependent taxa and 46 potential secondary losses, mostly single-host parasites.

## 12. Experimental indices (Phases 18–19)

IBVCI (per species) components: model-predicted vulnerability, climate-niche narrowness, range
restriction, recording decline, network importance, protection deficit, recent forest loss and
built-up share in occupied cells. CIPI (per 0.75° cell): observed species, threatened species, mean
vulnerability, mean network importance, protected-area gap, recent forest loss and built-up share.

Each component is converted to a 0–1 percentile rank. The default composite is an unweighted mean,
presented as a neutral reference rather than a justified weighting; callers can pass their own weights.
Items need at least two-thirds of the components to be ranked. 1,000 random weightings (Dirichlet(1),
fixed seed) give each item's median rank, 5th–95th percentile rank and share of draws in the top 10.
Components overlap (the model already uses range and protection), so some signals are counted twice.

## 13. Regional reports (Phase 20)

State reports are assembled from database queries by fixed templates; no language model writes text.
Every statement carries its evidence (the numbers it uses). Sections: overview, richness, threatened
species (official and unverified separately), notable species, temporal trends, protection, model
risk, CIPI priority and environmental pressures. District reports are not offered because records are
attributed to states only.

## 14. Reproducibility

- Pinned environment: `requirements-lock.txt` (Python 3.14.3).
- One command rebuilds everything from the raw files: `python scripts/run_pipeline.py`.
- Fixed seeds: GBIF sampling (`bioindia-2026`), cross-validation and index sensitivity (`20261027`).
- Model versions and their metrics are stored in `model_registry`; each prediction row names its version.
- Raw data, IUCN files, WDPA and models are not in git because of size and licence terms; the GBIF
  download request is, so the same download can be re-requested.

## 15. General limitations

- Occurrence records are presence-only and reflect where people record; there is no survey-effort
  correction, so richness, trends and concentration are partly maps of observers.
- Record counts are not population sizes; missing records do not mean absence or extinction.
- Most threatened-species coordinates are deliberately obscured by publishers; analyses that need
  location use only records within 10 km and say how many were left out.
- Precise elephant and sloth bear records come almost entirely from Tamil Nadu surveys.
- OSM protected-area outlines are community-mapped and may include buffer zones.
- State boundaries are geoBoundaries ADM1; attribution near borders and coasts is approximate.
- Correlation is not causation: climate, land-use and model associations do not show what threatens
  a species.
