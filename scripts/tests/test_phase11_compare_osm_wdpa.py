import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase11_compare_osm_wdpa import also_wildlife_pa, classify, dual_basis, parse_other_tags


class OsmClassifyTests(unittest.TestCase):
    def test_core_wildlife_classes(self) -> None:
        self.assertEqual(classify({"name": "Kaziranga National Park"}), "national_park")
        self.assertEqual(classify({"name": "Bori WLS"}), "wildlife_sanctuary")
        self.assertEqual(classify({"name": "Pakke Wildlife Sanctuary"}), "wildlife_sanctuary")
        self.assertEqual(classify({"name": "Tiruppadaimarathur Conservation Reserve"}), "conservation_community_reserve")

    def test_dual_named_tiger_reserves_also_count_as_wildlife_pa(self) -> None:
        for name in (
            "Sathyamangalam WLS/Tiger Reserve",
            "Tadoba Andhari National Park/Tiger Reserve",
            "Namdapha National Park / Tiger Reserve",
            "Similipal-Hadagarh WLS/Tiger Reserve",
            "Periyar National Park & Tiger Reserve",
        ):
            self.assertTrue(also_wildlife_pa({"name": name}), name)
        for name in ("Corbett Tiger Reserve", "Kaziranga National Park"):
            self.assertFalse(also_wildlife_pa({"name": name}), name)

    def test_manual_list_adds_anamalai_with_documented_basis(self) -> None:
        basis = dual_basis({"name": "Anamalai Tiger Reserve"})
        self.assertTrue(basis.startswith("manual list:"))
        self.assertIn("Indira Gandhi Wildlife Sanctuary and National Park", basis)
        self.assertEqual(dual_basis({"name": "Sathyamangalam WLS/Tiger Reserve"}), "name says National Park or WLS/Sanctuary")
        self.assertIsNone(dual_basis({"name": "Anamalai Hills Reserved Forest"}))

    def test_tiger_reserves_are_separate(self) -> None:
        self.assertEqual(classify({"name": "Tadoba Andhari National Park/Tiger Reserve"}), "tiger_reserve")

    def test_zones_and_proposed_sites_are_excluded(self) -> None:
        self.assertEqual(classify({"name": "Silent Valley National Park ESZ (Proposed)"}), "excluded_zone_or_proposed")
        self.assertEqual(classify({"name": "Radhanagari - Goa Tiger Corridor"}), "excluded_zone_or_proposed")
        self.assertEqual(classify({"name": "X", "protection_title": "Eco-Sensitive Zone"}), "excluded_zone_or_proposed")

    def test_forest_and_other(self) -> None:
        self.assertEqual(classify({"name": "Dhima Reserved Forest"}), "forest")
        self.assertEqual(classify({"name": "Yamuna Biodiversity Park"}), "other")

    def test_parse_other_tags(self) -> None:
        tags = parse_other_tags('"protect_class"=>"2","name:en"=>"Kanha National Park","wikidata"=>"Q1"')
        self.assertEqual(tags, {"protect_class": "2", "name:en": "Kanha National Park", "wikidata": "Q1"})


if __name__ == "__main__":
    unittest.main()
