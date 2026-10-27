"""Run the full BioIndia data pipeline in dependency order.

Usage:
  python scripts/run_pipeline.py                 # every step
  python scripts/run_pipeline.py --from phase9   # resume from the first step whose name contains 'phase9'
  python scripts/run_pipeline.py --list          # show the steps

Steps marked (network) call GBIF or GloBI web APIs. Raw downloads must already be in data/raw/ (see README).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
STEPS: list[list[str]] = [
    ["db_schema.py"],
    ["prepare_state_boundaries.py"],
    ["prepare_zoo_locations.py"],
    ["phase2_build_species_list.py"],  # (network) GBIF backbone matching
    ["phase2_load_species.py"],
    ["phase4_prepare_postgis_inputs.py"],
    ["phase4_load_postgis.py"],
    ["phase8_prepare_iucn_export.py"],
    ["phase8_import_conservation_assessments.py", "--input", "data/processed/iucn_assessments_import.csv"],
    ["phase11_load_wdpa.py"],
    ["phase11_compare_osm_wdpa.py"],
    ["phase11_load_osm.py"],
    ["phase11_subdivide_protected_areas.py"],
    ["phase9_sample_worldclim.py"],
    ["phase10_build_land_use_grid.py"],
    ["phase13_build_grid_metrics.py"],
    ["phase14_fetch_gbif_summaries.py"],  # (network) GBIF facet API
    ["phase16_fetch_globi.py"],  # (network) GloBI API
    ["phase16_load_interactions.py"],
    ["phase14_train_risk_model.py"],
    ["phase5_export_dashboard_data.py"],
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", help="Start at the first step whose script name contains this text.")
    parser.add_argument("--list", action="store_true", help="List the steps and exit.")
    args = parser.parse_args()
    steps = STEPS
    if args.start:
        positions = [i for i, step in enumerate(STEPS) if args.start in step[0]]
        if not positions:
            raise SystemExit(f"No step matches '{args.start}'.")
        steps = STEPS[positions[0]:]
    for number, step in enumerate(steps, start=1):
        if args.list:
            print(f"{number:2}. {' '.join(step)}")
            continue
        started = time.monotonic()
        print(f"[{number}/{len(steps)}] {' '.join(step)}", flush=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / step[0]), *step[1:]], cwd=SCRIPTS.parent)
        if result.returncode != 0:
            raise SystemExit(f"Step {step[0]} failed with exit code {result.returncode}; resume with --from {step[0].removesuffix('.py')}")
        print(f"    done in {time.monotonic() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
