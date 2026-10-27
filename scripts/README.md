# BioIndia pipeline scripts

Run the whole pipeline from the project root with `python scripts/run_pipeline.py` (`--list` shows the
order, `--from <step>` resumes). Setup, data sources and licences are in the main [README](../README.md);
the rules and numbers behind each step are in [docs/METHODS.md](../docs/METHODS.md).

| Script | Roadmap phase |
|---|---|
| `db_schema.py` | applies the Alembic migrations in `backend/migrations/` |
| `prepare_state_boundaries.py`, `prepare_zoo_locations.py` | reference layers |
| `phase2_build_species_list.py`, `phase2_load_species.py` | 2 - species list and GBIF taxonomy |
| `phase4_prepare_postgis_inputs.py`, `phase4_load_postgis.py` | 3–4 - GBIF screening, sampling, PostGIS load |
| `phase8_prepare_iucn_export.py`, `phase8_import_conservation_assessments.py` | 8 - IUCN assessments |
| `phase9_sample_worldclim.py` | 9 - climate |
| `phase10_download_landuse.sh`, `phase10_build_land_use_grid.py` | 10 - forest change, fragmentation, human pressure |
| `phase11_load_wdpa.py`, `phase11_compare_osm_wdpa.py`, `phase11_load_osm.py` | 11 - protected areas |
| `phase13_build_grid_metrics.py` | 13 - grid analytics |
| `phase14_fetch_gbif_summaries.py`, `phase14_train_risk_model.py` | 14–15 - risk model and SHAP |
| `phase16_fetch_globi.py`, `phase16_load_interactions.py` | 16 - interactions |
| `phase5_export_dashboard_data.py` | dashboard fallback files |

Kept for reference only (earlier prototype; they need source files that are not available):
`00_`–`06_*.py`, `phase1_finalize_outputs.py`, `phase3_build_occurrence_points.py`,
`phase4_build_dashboard_outputs.py`, `phase10_import_land_pressure.py`, `phase11_load_protected_areas.py`.

Unit tests for the quality rules: `python -m pytest -q scripts/tests`.
