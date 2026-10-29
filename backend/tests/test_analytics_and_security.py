import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from test_species_api import database_url


class Phase13AnalyticsTests(unittest.TestCase):
    """Run against PostGIS with analytics_grid_cells built by scripts/phase13_build_grid_metrics.py."""

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

    def test_hotspots_rank_by_chosen_component_without_composite_score(self) -> None:
        response = self.client.get("/api/v1/analytics/hotspots", params={"rank_by": "observed_species", "limit": 10})

        self.assertEqual(response.status_code, 200)
        cells = [feature["properties"] for feature in response.json()["features"]]
        self.assertEqual(len(cells), 10)
        self.assertEqual([c["observed_species"] for c in cells], sorted((c["observed_species"] for c in cells), reverse=True))
        self.assertNotIn("score", " ".join(cells[0]))
        self.assertIn("not officially recognised biodiversity hotspots", " ".join(response.json()["metadata"]["caveats"]))
        self.assertIn("habitat_pressure", response.json()["metadata"]["unavailable_components"])

    def test_rejects_unknown_ranking(self) -> None:
        self.assertEqual(self.client.get("/api/v1/analytics/hotspots", params={"rank_by": "magic"}).status_code, 422)

    def test_conservation_priority_applies_requested_thresholds(self) -> None:
        response = self.client.get("/api/v1/analytics/conservation-priority", params={"max_wildlife_pa_pct": 5, "min_threatened_species": 2})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["metadata"]["criteria"]["max_wildlife_pa_pct"], 5)
        for feature in payload["features"]:
            self.assertLessEqual(feature["properties"]["wildlife_pa_pct"], 5)
            self.assertGreaterEqual(feature["properties"]["threatened_species"], 2)
            # Flagship categories are unverified, so any cell counting one cannot be fully verified.
            if {"tiger", "elephant", "rhino", "bear", "croc"} & set(feature["properties"]["threatened_species_ids"]):
                self.assertFalse(feature["properties"]["threatened_status_verified"])

    def test_threatened_species_reports_unverified_categories(self) -> None:
        response = self.client.get("/api/v1/analytics/threatened-species")

        self.assertEqual(response.status_code, 200)
        species = {item["species_id"]: item for item in response.json()["species"]}
        self.assertTrue({"tiger", "elephant", "rhino", "bear", "croc"} <= set(species))
        self.assertTrue(all(item["category"] in {"CR", "EN", "VU"} for item in species.values()))
        self.assertEqual(species["tiger"]["category"], "EN")
        self.assertFalse(species["tiger"]["category_verified"])
        self.assertGreater(species["tiger"]["grid_cells_occupied"], 0)

    def test_map_aliases_match_gis_routes(self) -> None:
        self.assertEqual(self.client.get("/api/v1/map/hotspots").json(), self.client.get("/api/v1/gis/hotspots").json())
        response = self.client.get("/api/v1/map/occurrences", params={"species_id": "rhino", "state": "Assam", "within_10_km_only": "true", "limit": 5000})
        self.assertEqual(response.status_code, 200)
        properties = [feature["properties"] for feature in response.json()["features"]]
        self.assertTrue(properties)
        self.assertTrue(all(p["state"] == "Assam" and p["coordinate_uncertainty_class"] in {"precise", "moderate"} for p in properties))

    def test_map_rejects_reversed_year_range(self) -> None:
        response = self.client.get("/api/v1/map/occurrences", params={"year_from": 2025, "year_to": 2020})
        self.assertEqual(response.status_code, 422)


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_cors_allows_local_dashboard_only(self) -> None:
        allowed = self.client.get("/api/health", headers={"Origin": "http://127.0.0.1:5500"})
        other = self.client.get("/api/health", headers={"Origin": "https://example.com"})

        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://127.0.0.1:5500")
        self.assertIsNone(other.headers.get("access-control-allow-origin"))
        self.assertIsNone(allowed.headers.get("access-control-allow-credentials"))

    def test_cors_preflight_allows_post_for_the_dashboard_only(self) -> None:
        def preflight(origin: str, method: str):
            return self.client.options("/api/v1/reports/regional", headers={"Origin": origin, "Access-Control-Request-Method": method})

        self.assertEqual(preflight("http://127.0.0.1:5500", "POST").status_code, 200)
        self.assertNotEqual(preflight("https://example.com", "POST").status_code, 200)
        self.assertNotEqual(preflight("http://127.0.0.1:5500", "DELETE").status_code, 200)

    def test_output_endpoint_serves_only_dashboard_files(self) -> None:
        listed = {item["name"] for item in self.client.get("/api/datasets/outputs").json()["outputs"]}
        self.assertEqual(listed, {"state_species.json", "occurrence_points.json", "hotspots.geojson", "species_images.json"})
        for name in ("species_master.json", "osm_protected_areas.gpkg", "..%2Fraw%2Fgbif%2Fgbif_download_request.json"):
            self.assertEqual(self.client.get(f"/api/datasets/outputs/{name}").status_code, 404, name)


if __name__ == "__main__":
    unittest.main()
