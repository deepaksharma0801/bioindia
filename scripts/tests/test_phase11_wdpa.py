import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase11_load_wdpa import FOREST, OTHER, PROPOSED, WILDLIFE_PA, classify


class ClassifyTests(unittest.TestCase):
    def test_wildlife_protected_area_designations(self) -> None:
        for designation in (
            "National Park",
            "Wildlife Sanctuary",
            "Sanctuary",
            "Wildlife Sanctuary/ Bird Sanctuary",
            "Wildlife Sanctuary (Protected Area)",
            "Conservation Reserve",
            "Community Reserve",
        ):
            self.assertEqual(classify(designation, "Designated"), WILDLIFE_PA, designation)

    def test_forest_categories_are_separate(self) -> None:
        for designation in ("Reserve Forest", "Reserved Forest", "Protected Forest", "Protected Forest and Unclassed Forest"):
            self.assertEqual(classify(designation, "Designated"), FOREST, designation)

    def test_other_designations(self) -> None:
        for designation in ("Wetland of International Importance (Ramsar Site)", "Biodiversity Heritage Site", "Eco-Sensitive Zone", "Protected", None):
            self.assertEqual(classify(designation, "Designated"), OTHER, designation)

    def test_proposed_sites_are_excluded_from_every_layer(self) -> None:
        self.assertEqual(classify("National Park", "Proposed"), PROPOSED)
        self.assertEqual(classify("Proposed Reserve Forest", "Proposed"), PROPOSED)


if __name__ == "__main__":
    unittest.main()
