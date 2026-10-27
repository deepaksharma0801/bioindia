import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from test_species_api import database_url


class PredictionApiTests(unittest.TestCase):
    """Run against PostGIS with a model trained by scripts/phase14_train_risk_model.py."""

    @classmethod
    def setUpClass(cls) -> None:
        url = database_url()
        if url is None:
            raise unittest.SkipTest("PostGIS database with loaded occurrences is not reachable.")
        cls.environment = mock.patch.dict(os.environ, {"DATABASE_URL": url})
        cls.environment.start()
        cls.client = TestClient(app)
        if cls.client.get("/api/v1/model-info").status_code != 200:
            raise unittest.SkipTest("No trained risk model in the database.")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.environment.stop()

    def test_prediction_is_labelled_as_model_output(self) -> None:
        payload = self.client.get("/api/v1/prediction/species/tiger").json()

        self.assertIn("not an official IUCN", payload["disclaimer"])
        self.assertTrue(0.0 <= payload["predicted_threatened_probability"] <= 1.0)
        self.assertEqual(payload["prediction_type"], "unlabelled")

    def test_training_species_get_out_of_fold_predictions(self) -> None:
        payload = self.client.get("/api/v1/prediction/species/ardeola_grayii").json()
        self.assertEqual(payload["prediction_type"], "out_of_fold")
        self.assertEqual(payload["official_iucn_category"], "LC")

    def test_explanation_lists_shap_contributions_without_causal_claims(self) -> None:
        payload = self.client.get("/api/v1/prediction/species/tiger/explanation").json()

        self.assertGreater(len(payload["top_contributions"]), 0)
        self.assertIn("do not establish ecological causes", payload["explanation_note"])
        self.assertTrue(all(item["direction"] in {"raises predicted risk", "lowers predicted risk"} for item in payload["top_contributions"]))

    def test_model_info_and_performance(self) -> None:
        info = self.client.get("/api/v1/model-info").json()
        performance = self.client.get("/api/v1/model-performance").json()

        self.assertNotIn("has_precise_records", [feature["name"] for feature in info["features"]])
        self.assertGreater(info["training_data"]["labelled_species"], 100)
        self.assertIn(performance["selected_model"], performance["candidates"])
        self.assertGreater(performance["candidates"][performance["selected_model"]]["pr_auc"]["mean"], performance["pr_auc_baseline_prevalence"])

    def test_unknown_species_is_404(self) -> None:
        self.assertEqual(self.client.get("/api/v1/prediction/species/lion").status_code, 404)


if __name__ == "__main__":
    unittest.main()
