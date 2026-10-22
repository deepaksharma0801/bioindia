import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collections import namedtuple

from shapely.geometry import box

from phase11_load_osm import PA_CLASS_BY_OSM_CLASS, build_rows
from phase11_load_wdpa import LOADED_CLASSES

Feature = namedtuple("Feature", "osm_id name osm_class also_wildlife_pa dual_basis geometry")


class LayerSplitTests(unittest.TestCase):
    def test_osm_supplies_wildlife_and_tiger_reserve_layers(self) -> None:
        self.assertEqual(
            PA_CLASS_BY_OSM_CLASS,
            {
                "national_park": "wildlife_pa",
                "wildlife_sanctuary": "wildlife_pa",
                "conservation_community_reserve": "wildlife_pa",
                "tiger_reserve": "tiger_reserve",
            },
        )

    def test_wdpa_supplies_only_forest_and_other_layers(self) -> None:
        self.assertEqual(LOADED_CLASSES, ("forest", "other_designation"))

    def test_dual_named_tiger_reserve_loads_in_both_layers(self) -> None:
        rows, dual = build_rows([
            Feature("way/1", "Sathyamangalam WLS/Tiger Reserve", "tiger_reserve", True, "name says National Park or WLS/Sanctuary", box(77, 11, 78, 12)),
            Feature("way/2", "Corbett Tiger Reserve", "tiger_reserve", False, None, box(76, 10, 77, 11)),
            Feature("way/3", "Kanha Nationalpark", "national_park", False, None, box(80, 22, 81, 23)),
        ])
        self.assertEqual(
            [(row["protected_area_id"], row["pa_class"]) for row in rows],
            [
                ("OSM:way/1", "tiger_reserve"),
                ("OSM:way/1#wildlife_pa", "wildlife_pa"),
                ("OSM:way/2", "tiger_reserve"),
                ("OSM:way/3", "wildlife_pa"),
            ],
        )
        self.assertEqual(dual, [{"osm_id": "way/1", "name": "Sathyamangalam WLS/Tiger Reserve", "basis": "name says National Park or WLS/Sanctuary"}])

    def test_sources_do_not_overlap(self) -> None:
        self.assertFalse(set(PA_CLASS_BY_OSM_CLASS.values()) & set(LOADED_CLASSES))


if __name__ == "__main__":
    unittest.main()
