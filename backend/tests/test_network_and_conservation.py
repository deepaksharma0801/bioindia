import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from test_species_api import database_url


class NetworkAndConservationTests(unittest.TestCase):
    """Run against PostGIS with IUCN assessments (Phase 8) and GloBI interactions (Phase 16) loaded."""

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

    def test_species_network_reports_documented_partners_without_self(self) -> None:
        payload = self.client.get("/api/v1/network/species/tiger").json()

        self.assertGreater(payload["documented_partner_count"], 0)
        self.assertNotIn("tiger", payload["partners_in_platform"])
        self.assertTrue(all(row["evidence_type"] == "DOCUMENTED" for row in payload["documented_interactions"]))
        self.assertTrue(all(row["evidence_type"] == "CO_OCCURRENCE_ASSOCIATION" for row in payload["co_occurrence_associations"]))
        self.assertIn("not from observations in India", " ".join(payload["notes"]))

    def test_top_partners_summarise_documented_links(self) -> None:
        payload = self.client.get("/api/v1/network/species/tiger").json()
        top = payload["top_partners"]
        documented = {row["partner_name"] for row in payload["documented_interactions"]}

        self.assertLessEqual(len(top), 10)
        self.assertEqual([p["records"] for p in top], sorted((p["records"] for p in top), reverse=True))
        self.assertTrue(all(p["name"] in documented and p["types"] for p in top))

    def test_ecosystem_network_avoids_keystone_language(self) -> None:
        payload = self.client.get("/api/v1/network/ecosystem/Assam").json()

        self.assertIn("not keystone", payload["terminology"])
        self.assertGreaterEqual(payload["metrics"]["species_recorded"], 1)
        self.assertEqual(self.client.get("/api/v1/network/ecosystem/Atlantis").status_code, 404)

    def test_subspecies_assessment_is_labelled_not_global(self) -> None:
        payload = self.client.get("/api/v1/species/panthera_pardus/conservation").json()

        self.assertEqual(payload["species"]["official_assessment_taxon_level"], "subspecies")
        self.assertEqual(payload["official_assessment"]["data"]["assessed_taxon_name"], "Panthera pardus ssp. fusca")
        self.assertIn("not the species' global status", payload["official_assessment"]["note"])

    def test_species_level_assessment_has_provenance(self) -> None:
        data = self.client.get("/api/v1/species/ardeola_grayii/conservation").json()["official_assessment"]["data"]

        self.assertEqual(data["taxon_level"], "species")
        self.assertTrue(data["source_url"].startswith("https://www.iucnredlist.org/species/"))
        self.assertEqual(str(data["retrieval_date"]), "2026-10-21")


if __name__ == "__main__":
    unittest.main()
