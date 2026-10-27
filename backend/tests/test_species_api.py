import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app


DEFAULT_DATABASE_URL = "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia"


def database_url() -> str | None:
    """The loaded development database, or None when it cannot be reached."""
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=3) as connection:
            connection.execute("SELECT 1 FROM occurrences LIMIT 1")
    except Exception:
        return None
    return url


class SpeciesApiTests(unittest.TestCase):
    """Run against the PostGIS database loaded by scripts/phase4_load_postgis.py."""

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

    def test_species_list_reads_database(self) -> None:
        response = self.client.get("/api/v1/species")

        self.assertEqual(response.status_code, 200)
        species = {item["species_id"]: item for item in response.json()["species"]}
        self.assertGreaterEqual(len(species), 5)
        self.assertTrue({"tiger", "elephant", "rhino", "bear", "croc"} <= set(species))
        self.assertTrue(all(species[flagship]["observation_record_count"] > 0 for flagship in ("tiger", "elephant", "rhino", "bear", "croc")))

    def test_species_search_and_detail(self) -> None:
        search_response = self.client.get("/api/v1/species/search", params={"query": "tiger"})
        detail_response = self.client.get("/api/v1/species/tiger")

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["species"][0]["species_id"], "tiger")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["source_reported_iucn_status"], "EN")
        self.assertIsNone(detail["official_iucn_status"])

    def test_unknown_species_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/species/lion").status_code, 404)

    def test_species_occurrences_and_trend_are_available(self) -> None:
        occurrence_response = self.client.get("/api/v1/species/tiger/occurrences")
        trend_response = self.client.get("/api/v1/species/tiger/trend")

        self.assertEqual(occurrence_response.status_code, 200)
        species = occurrence_response.json()["species"]
        self.assertEqual(len(species), 1)
        self.assertGreater(len(species[0]["points"]), 0)
        self.assertIn("uncertaintyClass", species[0]["points"][0])
        self.assertEqual(trend_response.status_code, 200)
        self.assertEqual(trend_response.json()["years"][0], 2000)
        self.assertIn("not a population-abundance estimate", trend_response.json()["methodology_note"])

    def test_state_profiles_use_dashboard_format(self) -> None:
        response = self.client.get("/api/v1/species/state-profiles")

        self.assertEqual(response.status_code, 200)
        assam = {entry["species_id"]: entry for entry in response.json()["Assam"]}
        self.assertGreater(assam["rhino"]["obs"], 0)
        self.assertEqual(assam["rhino"]["st"], "vu")
        self.assertFalse(assam["rhino"]["status_verified"])
        self.assertIsNone(assam["rhino"]["eri"])

    def test_species_intelligence_discloses_derived_and_missing_data(self) -> None:
        response = self.client.get("/api/v1/species/tiger/intelligence")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["conservation_assessment"]["official_assessment_verified"])
        self.assertIn("not population-abundance estimates", payload["occurrence_history"]["note"])
        self.assertEqual(payload["data_gaps"]["environmental_exposure"], "not yet integrated")
        self.assertFalse(payload["derived_watchlist_signal"]["available"])
        self.assertGreater(payload["protected_area_coverage"]["records_used"]["count"], 0)

    def test_gis_hotspots_and_boundary_metadata_are_available(self) -> None:
        hotspot_response = self.client.get("/api/v1/gis/hotspots")
        boundary_response = self.client.get("/api/v1/gis/state-boundaries/info")

        self.assertEqual(hotspot_response.status_code, 200)
        self.assertEqual(hotspot_response.json()["type"], "FeatureCollection")
        self.assertEqual(len(hotspot_response.json()["features"]), 9)
        self.assertIn("not population abundance", hotspot_response.json()["metadata"]["caveat"])
        self.assertIn("not officially recognised biodiversity hotspots", hotspot_response.json()["metadata"]["caveat"])
        self.assertEqual(boundary_response.status_code, 200)
        self.assertEqual(boundary_response.json()["download_url"], "/api/v1/gis/state-boundaries")

    def test_gis_occurrence_rejects_incomplete_bounding_box(self) -> None:
        response = self.client.get("/api/v1/gis/occurrences", params={"west": 70, "south": 10})

        self.assertEqual(response.status_code, 422)
        self.assertIn("must be supplied together", response.json()["detail"])

    def test_conservation_endpoint_keeps_unverified_source_data_separate(self) -> None:
        response = self.client.get("/api/v1/species/tiger/conservation")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["official_assessment"]["available"])
        self.assertEqual(payload["source_reported_category"]["category"], "EN")
        self.assertIn("not an independently verified", payload["source_reported_category"]["note"])

    def test_environment_endpoint_returns_real_worldclim_metadata(self) -> None:
        response = self.client.get("/api/v1/species/tiger/environment")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["metadata"]["reference_period"], "1970-2000")
        self.assertGreater(payload["profile"]["sampled_occurrence_count"], 0)
        self.assertGreater(payload["profile"]["annual_mean_temperature_c"], 10)

    def test_land_pressure_is_explicitly_unavailable_without_an_authorized_import(self) -> None:
        response = self.client.get("/api/v1/species/tiger/land-pressure")

        self.assertEqual(response.status_code, 503)
        self.assertIn("not available", response.json()["detail"])


class WithoutDatabaseTests(unittest.TestCase):
    """With no DATABASE_URL, database-backed endpoints answer 503 rather than empty data."""

    def setUp(self) -> None:
        environment = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
        patcher = mock.patch.dict(os.environ, environment, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def test_species_endpoints_report_unavailable(self) -> None:
        for path in ("/api/v1/species", "/api/v1/species/tiger", "/api/v1/species/state-profiles", "/api/v1/gis/hotspots"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503, path)
            self.assertIn("database is not available", response.json()["detail"], path)

    def test_database_backed_time_series_reports_unavailable_without_database(self) -> None:
        species_response = self.client.get("/api/v1/species/tiger/observation-time-series")
        biodiversity_response = self.client.get("/api/v1/analytics/biodiversity-trends")

        self.assertEqual(species_response.status_code, 503)
        self.assertEqual(biodiversity_response.status_code, 503)
        self.assertIn("time-series", species_response.json()["detail"])

    def test_database_backed_concentration_reports_unavailable_without_database(self) -> None:
        response = self.client.get("/api/v1/analytics/biodiversity-concentration")

        self.assertEqual(response.status_code, 503)
        self.assertIn("concentration", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
