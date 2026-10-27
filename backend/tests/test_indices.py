import math
import os
import unittest
from unittest import mock

import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.indices import IBVCI_COMPONENTS, IndexError_, composite, parse_weights, percentile_rank
from test_species_api import database_url


class IndexMathTests(unittest.TestCase):
    def test_percentile_rank_keeps_missing(self) -> None:
        ranks = percentile_rank(np.array([3.0, np.nan, 1.0, 2.0]))
        self.assertEqual(list(ranks[[0, 2, 3]]), [1.0, 0.0, 0.5])
        self.assertTrue(math.isnan(ranks[1]))
        self.assertEqual(list(percentile_rank(np.array([1.0, 2.0]), invert=True)), [1.0, 0.0])

    def test_composite_drops_missing_and_requires_two_thirds(self) -> None:
        matrix = np.array([[1.0, 0.0, 0.5], [1.0, np.nan, 0.5], [1.0, np.nan, np.nan]])
        scores = composite(matrix, np.array([1.0, 1.0, 1.0]))
        self.assertAlmostEqual(scores[0], 0.5)
        self.assertAlmostEqual(scores[1], 0.75)
        self.assertTrue(math.isnan(scores[2]))

    def test_weights_parsing(self) -> None:
        self.assertEqual(parse_weights(None, IBVCI_COMPONENTS), {name: 1.0 for name in IBVCI_COMPONENTS})
        self.assertEqual(parse_weights("extinction_vulnerability:2", IBVCI_COMPONENTS), {"extinction_vulnerability": 2.0})
        for bad in ("magic:1", "extinction_vulnerability:x", "extinction_vulnerability:-1", "extinction_vulnerability:0"):
            with self.assertRaises(IndexError_, msg=bad):
                parse_weights(bad, IBVCI_COMPONENTS)


class IndexApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        url = database_url()
        if url is None:
            raise unittest.SkipTest("PostGIS database with loaded occurrences is not reachable.")
        cls.environment = mock.patch.dict(os.environ, {"DATABASE_URL": url})
        cls.environment.start()
        cls.client = TestClient(app)
        if cls.client.get("/api/v1/indices/ibvci", params={"limit": 1}).status_code != 200:
            raise unittest.SkipTest("Index inputs are not available.")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.environment.stop()

    def test_ibvci_is_experimental_with_separate_components(self) -> None:
        payload = self.client.get("/api/v1/indices/ibvci", params={"limit": 5}).json()

        self.assertEqual(payload["label"], "EXPERIMENTAL RESEARCH METRIC")
        self.assertEqual(payload["unavailable_components"], {})
        self.assertIn("habitat_loss", payload["components"])
        first = payload["species"][0]
        self.assertEqual(set(first["components"]), set(IBVCI_COMPONENTS))
        self.assertLessEqual(first["sensitivity"]["rank_p05"], first["sensitivity"]["rank_p95"])
        self.assertEqual([s["rank"] for s in payload["species"]], [1, 2, 3, 4, 5])

    def test_custom_weights_change_ranking(self) -> None:
        default = [s["species_id"] for s in self.client.get("/api/v1/indices/ibvci", params={"limit": 10}).json()["species"]]
        custom = self.client.get("/api/v1/indices/ibvci", params={"limit": 10, "weights": "protection_deficit:1"}).json()
        self.assertEqual(custom["weights"], {"protection_deficit": 1.0})
        self.assertNotEqual(default, [s["species_id"] for s in custom["species"]])

    def test_cipi_cells_and_state_filter(self) -> None:
        payload = self.client.get("/api/v1/indices/cipi", params={"state": "Kerala", "limit": 5}).json()
        self.assertTrue(payload["cells"])
        self.assertTrue(all(cell["dominant_state"] == "Kerala" for cell in payload["cells"]))
        self.assertIn("record_count", payload["cells"][0])

    def test_errors(self) -> None:
        self.assertEqual(self.client.get("/api/v1/indices/ibvci", params={"weights": "magic:1"}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/indices/ibvci/lion").status_code, 404)


if __name__ == "__main__":
    unittest.main()
