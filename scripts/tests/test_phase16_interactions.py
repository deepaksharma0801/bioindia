import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase16_load_interactions import binomial, evidence_type, normalise


SPECIES = {"Panthera tigris": "tiger", "Rhinoceros unicornis": "rhino"}


class InteractionNormaliseTests(unittest.TestCase):
    def test_binomial(self) -> None:
        self.assertEqual(binomial("Panthera tigris tigris"), "Panthera tigris")
        self.assertEqual(binomial("Rucervus duvaucelii ranjitsinhi"), "Rucervus duvaucelii")
        self.assertIsNone(binomial("Cervidae"))
        self.assertIsNone(binomial("Insecta sp"))
        self.assertIsNone(binomial(None))

    def test_co_occurrence_is_never_documented(self) -> None:
        self.assertEqual(evidence_type("coOccursWith"), "CO_OCCURRENCE_ASSOCIATION")
        self.assertEqual(evidence_type("adjacentTo"), "CO_OCCURRENCE_ASSOCIATION")
        self.assertEqual(evidence_type("eats"), "DOCUMENTED")

    def test_links_platform_species_on_either_side(self) -> None:
        row = {"source_taxon_name": "Panthera tigris tigris", "interaction_type": "eats", "target_taxon_name": "Rhinoceros unicornis",
               "study_citation": "Paper A", "study_source_citation": "Dataset X"}
        record = normalise(row, SPECIES, "2026-10-26")
        self.assertEqual((record["source_species_id"], record["target_species_id"]), ("tiger", "rhino"))
        self.assertEqual(record["evidence_type"], "DOCUMENTED")
        self.assertEqual(record["data_source"], "GloBI")

    def test_skips_rows_without_a_platform_species_or_names(self) -> None:
        self.assertIsNone(normalise({"source_taxon_name": "Canis lupus", "interaction_type": "eats", "target_taxon_name": "Ovis aries"}, SPECIES, "2026-10-26"))
        self.assertIsNone(normalise({"source_taxon_name": "", "interaction_type": "eats", "target_taxon_name": "Panthera tigris"}, SPECIES, "2026-10-26"))

    def test_inverse_types_are_turned_round(self) -> None:
        forward = normalise({"source_taxon_name": "Panthera tigris", "interaction_type": "eats", "target_taxon_name": "Rhinoceros unicornis",
                             "study_citation": "Paper A"}, SPECIES, "2026-10-26")
        inverse = normalise({"source_taxon_name": "Rhinoceros unicornis", "interaction_type": "eatenBy", "target_taxon_name": "Panthera tigris",
                             "study_citation": "Paper A"}, SPECIES, "2026-10-26")
        self.assertEqual((inverse["source_species_id"], inverse["interaction_type"], inverse["target_species_id"]), ("tiger", "eats", "rhino"))
        self.assertEqual(forward["interaction_id"], inverse["interaction_id"])

    def test_identical_records_share_an_id(self) -> None:
        row = {"source_taxon_name": "Panthera tigris", "interaction_type": "eats", "target_taxon_name": "Axis axis", "study_citation": "Paper A"}
        self.assertEqual(normalise(row, SPECIES, "2026-10-26")["interaction_id"], normalise(dict(row), SPECIES, "2026-10-27")["interaction_id"])


if __name__ == "__main__":
    unittest.main()
