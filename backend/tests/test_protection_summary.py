import unittest

from app.services.protection import PROTECTION_QUERY, summarize_protection


def query_result(**overrides):
    result = {
        "occurrence_record_count": 650,
        "eligible_record_count": 40,
        "coarse_records_left_out": 600,
        "unknown_uncertainty_records_left_out": 10,
        "wildlife_pa": 30,
        "tiger_reserve": 8,
        "forest": 20,
        "other_designation": 2,
        "source_versions": ["OSM_geofabrik_india_2026-10-22", "WDPA_WDOECM_Oct2026_Public_IND"],
    }
    result.update(overrides)
    return result


class ProtectionSummaryTests(unittest.TestCase):
    def test_percentages_use_only_records_within_10_km(self) -> None:
        summary = summarize_protection(query_result())

        self.assertEqual(summary["occurrence_record_count"], 650)
        self.assertEqual(summary["records_used"]["count"], 40)
        self.assertFalse(summary["records_used"]["small_sample_warning"])
        self.assertEqual(summary["wildlife_protected_areas"], {"records_intersecting": 30, "record_intersection_percent": 75.0})
        self.assertEqual(summary["reported_separately"]["tiger_reserves"]["record_intersection_percent"], 20.0)
        self.assertEqual(summary["reported_separately"]["legal_forest_categories"]["record_intersection_percent"], 50.0)

    def test_left_out_records_are_reported(self) -> None:
        left_out = summarize_protection(query_result())["records_left_out"]
        self.assertEqual(left_out["coarse_over_10_km"], 600)
        self.assertEqual(left_out["uncertainty_not_stated"], 10)

    def test_small_sample_is_flagged(self) -> None:
        summary = summarize_protection(query_result(eligible_record_count=9, wildlife_pa=7))
        self.assertTrue(summary["records_used"]["small_sample_warning"])
        self.assertEqual(summary["wildlife_protected_areas"]["record_intersection_percent"], 77.78)

    def test_no_eligible_records_gives_null_percentages(self) -> None:
        summary = summarize_protection(query_result(eligible_record_count=0, wildlife_pa=0, tiger_reserve=0, forest=0, other_designation=0))
        self.assertIsNone(summary["wildlife_protected_areas"]["record_intersection_percent"])
        self.assertEqual(summary["records_left_out"]["coarse_over_10_km"], 600)

    def test_species_without_records_returns_none(self) -> None:
        self.assertIsNone(summarize_protection({"occurrence_record_count": 0}))

    def test_query_counts_every_class_on_eligible_records(self) -> None:
        for pa_class in ("wildlife_pa", "tiger_reserve", "forest", "other_designation"):
            self.assertIn(f"pa.pa_class = '{pa_class}'", PROTECTION_QUERY)
            self.assertIn(f"AS {pa_class}", PROTECTION_QUERY)
        self.assertEqual(PROTECTION_QUERY.count("coordinate_uncertainty_class = ANY(%(eligible)s) AND EXISTS"), 4)


if __name__ == "__main__":
    unittest.main()
