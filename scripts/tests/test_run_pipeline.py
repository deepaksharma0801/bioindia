import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run_pipeline import SCRIPTS, STEPS


class PipelineOrderTests(unittest.TestCase):
    def position(self, script: str) -> int:
        return [step[0] for step in STEPS].index(script)

    def test_every_step_exists(self) -> None:
        for step in STEPS:
            self.assertTrue((SCRIPTS / step[0]).exists(), step[0])

    def test_schema_runs_first(self) -> None:
        self.assertEqual(STEPS[0][0], "db_schema.py")

    def test_dependencies_run_before_their_consumers(self) -> None:
        before = [
            ("prepare_zoo_locations.py", "phase4_load_postgis.py"),
            ("phase4_prepare_postgis_inputs.py", "phase4_load_postgis.py"),
            ("phase8_prepare_iucn_export.py", "phase8_import_conservation_assessments.py"),
            ("phase11_load_osm.py", "phase13_build_grid_metrics.py"),
            ("phase11_load_osm.py", "phase11_subdivide_protected_areas.py"),
            ("phase10_build_land_use_grid.py", "phase13_build_grid_metrics.py"),
            ("phase9_sample_worldclim.py", "phase14_train_risk_model.py"),
            ("phase10_build_land_use_grid.py", "phase14_train_risk_model.py"),
            ("phase14_fetch_gbif_summaries.py", "phase14_train_risk_model.py"),
            ("phase13_build_grid_metrics.py", "phase5_export_dashboard_data.py"),
        ]
        for first, then in before:
            self.assertLess(self.position(first), self.position(then), f"{first} before {then}")


if __name__ == "__main__":
    unittest.main()
