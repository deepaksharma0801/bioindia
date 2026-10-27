import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from test_species_api import database_url


class LandUseApiTests(unittest.TestCase):
    """Run against PostGIS after scripts/phase10_build_land_use_grid.py."""

    @classmethod
    def setUpClass(cls) -> None:
        url = database_url()
        if url is None:
            raise unittest.SkipTest("PostGIS database with loaded occurrences is not reachable.")
        cls.environment = mock.patch.dict(os.environ, {"DATABASE_URL": url})
        cls.environment.start()
        cls.client = TestClient(app)
        response = cls.client.get("/api/v1/land-use/states")
        if response.status_code != 200:
            raise unittest.SkipTest("Land-use grid has not been built.")
        cls.states = {item["state"]: item for item in response.json()["states"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.environment.stop()

    def test_every_state_has_consistent_shares(self) -> None:
        self.assertGreaterEqual(len(self.states), 30)
        for state in self.states.values():
            self.assertLessEqual(state["forest_2000_km2"], state["land_km2"] + 1, state["state"])
            self.assertLessEqual(state["forest_loss_2001_2024_km2"], state["forest_2000_km2"] + 1, state["state"])
            self.assertLessEqual(state["recent_forest_loss_2015_2024_pct"] or 0, state["forest_loss_pct_of_2000_forest"] or 0)

    def test_state_detail_series_adds_up(self) -> None:
        payload = self.client.get("/api/v1/land-use/states/assam").json()
        series = payload["forest_loss_km2_by_year"]

        self.assertEqual(payload["state"], "Assam")
        self.assertEqual(list(series), [str(year) for year in range(2001, 2025)])
        self.assertAlmostEqual(sum(series.values()), payload["forest_loss_2001_2024_km2"], delta=1)
        self.assertIn("not natural forest", payload["metadata"]["forest_definition"])

    def test_state_land_area_is_plausible(self) -> None:
        # Rajasthan is about 342,000 km2; cells are attributed by centroid, so allow a few percent.
        self.assertAlmostEqual(self.states["Rajasthan"]["land_km2"], 342_000, delta=342_000 * 0.05)

    def test_unknown_state_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/land-use/states/Atlantis").status_code, 404)

    def test_report_states_pressures_with_evidence(self) -> None:
        report = self.client.post("/api/v1/reports/regional", json={"region": "Assam"}).json()
        pressures = report["sections"]["environmental_pressures"]

        self.assertIn("Global Forest Change", pressures[0]["text"])
        self.assertIn("forest_loss_km2", pressures[1]["evidence"])
        self.assertIn("do not show effects on any species", pressures[-1]["text"])


if __name__ == "__main__":
    unittest.main()
