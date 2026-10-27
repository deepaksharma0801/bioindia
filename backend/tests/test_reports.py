import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from test_species_api import database_url


class RegionalReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        url = database_url()
        if url is None:
            raise unittest.SkipTest("PostGIS database with loaded occurrences is not reachable.")
        cls.environment = mock.patch.dict(os.environ, {"DATABASE_URL": url})
        cls.environment.start()
        cls.client = TestClient(app)
        cls.report = cls.client.post("/api/v1/reports/regional", json={"region": "Kerala"}).json()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.environment.stop()

    def test_every_statement_carries_evidence(self) -> None:
        for section, statements in self.report["sections"].items():
            for statement in statements:
                self.assertTrue(statement["text"], section)
                self.assertIsInstance(statement["evidence"], dict, section)
                self.assertTrue(statement["evidence"], section)

    def test_required_sections_and_honest_labels(self) -> None:
        sections = self.report["sections"]
        for name in ("biodiversity_overview", "species_richness", "threatened_species", "notable_species", "risk_indicators", "environmental_pressures"):
            self.assertIn(name, sections)
        self.assertIn("MODEL PREDICTION", sections["risk_indicators"][0]["text"])
        self.assertIn("not a population trend", sections["temporal_trends"][0]["text"])

    def test_overview_numbers_match_the_evidence(self) -> None:
        overview = self.report["sections"]["biodiversity_overview"][0]
        self.assertIn(f"{overview['evidence']['records']:,}", overview["text"])
        self.assertIn(str(overview["evidence"]["species"]), overview["text"])

    def test_markdown_and_unknown_region(self) -> None:
        self.assertTrue(self.report["markdown"].startswith("# Biodiversity report: Kerala"))
        self.assertEqual(self.client.post("/api/v1/reports/regional", json={"region": "Atlantis"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
