import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services.simulation import _cascade
from test_species_api import database_url


class CascadeRuleTests(unittest.TestCase):
    """The propagation rule on a hand-made network (no database needed)."""

    def test_threshold_and_steps(self) -> None:
        # A predator eats B and C; B is eaten by D (D depends on B only); E depends on D and F.
        dependencies = {"predator": {"B", "C"}, "D": {"B"}, "E": {"D", "F"}, "G": {"E"}}
        self.assertEqual(_cascade(dependencies, "B", 0.5, 3), [{"predator", "D"}, {"E"}, {"G"}])
        self.assertEqual(_cascade(dependencies, "B", 0.75, 3), [{"D"}])
        self.assertEqual(_cascade(dependencies, "B", 0.5, 1), [{"predator", "D"}])

    def test_nothing_propagates_without_dependents(self) -> None:
        self.assertEqual(_cascade({"A": {"B"}}, "Z", 0.5, 3), [])


class CascadeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        url = database_url()
        if url is None:
            raise unittest.SkipTest("PostGIS database with loaded occurrences is not reachable.")
        cls.environment = mock.patch.dict(os.environ, {"DATABASE_URL": url})
        cls.environment.start()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.environment.stop()

    def test_scenario_is_labelled_and_reports_sensitivity(self) -> None:
        payload = self.client.post("/api/v1/simulation/extinction-cascade", json={"species_id": "tiger"}).json()

        self.assertEqual(payload["label"], "SCENARIO SIMULATION")
        self.assertGreater(payload["summary"]["directly_dependent_taxa"], 0)
        counts = payload["sensitivity"]
        self.assertGreaterEqual(counts["threshold_0.25"], counts["threshold_0.5"])
        self.assertGreaterEqual(counts["threshold_0.5"], counts["threshold_0.75"])
        self.assertTrue(payload["assumptions"])

    def test_invalid_requests(self) -> None:
        self.assertEqual(self.client.post("/api/v1/simulation/extinction-cascade", json={"species_id": "lion"}).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/simulation/extinction-cascade", json={"species_id": "tiger", "threshold": 2}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/simulation/extinction-cascade", json={"species_id": "tiger", "region": "Atlantis"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
