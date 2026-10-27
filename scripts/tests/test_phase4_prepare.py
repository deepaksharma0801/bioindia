import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase4_prepare_postgis_inputs import kept_in_sample, parse_event_date, pg_array, sampling_fractions, screen, uncertainty_class


SPECIES_BY_KEY = {"5219416": "tiger"}


def gbif_row(**overrides):
    row = {
        "gbifID": "100", "datasetKey": "d1", "speciesKey": "5219416", "species": "Panthera tigris", "infraspecificEpithet": "tigris",
        "scientificName": "Panthera tigris tigris", "verbatimScientificName": "Panthera tigris",
        "occurrenceStatus": "PRESENT", "basisOfRecord": "HUMAN_OBSERVATION", "establishmentMeans": "", "locality": "Kanha",
        "decimalLatitude": "23.5", "decimalLongitude": "80.1", "coordinateUncertaintyInMeters": "25000",
        "eventDate": "2021-03-04T06:30", "year": "2021", "month": "3", "day": "4",
        "issue": "COORDINATE_ROUNDED;CONTINENT_DERIVED_FROM_COORDINATES", "license": "CC_BY_NC_4_0", "recordedBy": "Asha R",
    }
    row.update(overrides)
    return row


class ParseEventDateTests(unittest.TestCase):
    def test_precisions(self) -> None:
        self.assertEqual(parse_event_date("2021-03-04T06:30", "2021", "3", "4"), (date(2021, 3, 4), "day", None))
        self.assertEqual(parse_event_date("2019-07", "2019", "7", ""), (date(2019, 7, 1), "month", None))
        self.assertEqual(parse_event_date("1998", "1998", "", ""), (date(1998, 1, 1), "year", None))

    def test_falls_back_to_year_fields(self) -> None:
        self.assertEqual(parse_event_date("", "2005", "11", ""), (date(2005, 11, 1), "month", None))

    def test_ranges(self) -> None:
        self.assertEqual(parse_event_date("2010-01-01/2010-12-31", "2010", "", ""), (date(2010, 1, 1), "day", None))
        self.assertEqual(parse_event_date("2001/2004", "", "", "")[2], "date_range_spans_years")

    def test_missing_and_impossible(self) -> None:
        self.assertEqual(parse_event_date("", "", "", "")[2], "missing_date")
        self.assertEqual(parse_event_date("2999-01-01", "2999", "1", "1")[2], "impossible_date")


class ScreenTests(unittest.TestCase):
    def test_coarse_record_is_kept_and_flagged(self) -> None:
        record, reason = screen(gbif_row(), SPECIES_BY_KEY)
        self.assertIsNone(reason)
        self.assertEqual(record["occurrence_id"], "GBIF:100")
        self.assertEqual(record["species_id"], "tiger")
        self.assertEqual(record["coordinate_uncertainty_class"], "coarse")
        self.assertIn("coordinate_rounded", record["quality_flags"])
        self.assertIn("date_precision_day", record["quality_flags"])
        self.assertEqual(record["recorded_by"], "Asha R")

    def test_exclusion_reasons(self) -> None:
        cases = {
            "unmatched_species": gbif_row(speciesKey="999"),
            "occurrence_status_not_present": gbif_row(occurrenceStatus="ABSENT"),
            "basis_of_record_fossil_specimen": gbif_row(basisOfRecord="FOSSIL_SPECIMEN"),
            "basis_of_record_living_specimen": gbif_row(basisOfRecord="LIVING_SPECIMEN"),
            "non_native_subspecies_likely_captive": gbif_row(infraspecificEpithet="altaica"),
            "captive_or_managed": gbif_row(establishmentMeans="managed"),
            "missing_coordinates": gbif_row(decimalLatitude=""),
            "gbif_geospatial_issue_country_coordinate_mismatch": gbif_row(issue="COUNTRY_COORDINATE_MISMATCH"),
            "missing_date": gbif_row(eventDate="", year="", month="", day=""),
        }
        for expected, row in cases.items():
            self.assertEqual(screen(row, SPECIES_BY_KEY), (None, expected), expected)

    def test_captive_locality_text(self) -> None:
        mammal = {"kingdom": "Animalia", "class": "Mammalia"}
        for locality in ("Nehru Zoological Park, Hyderabad", "Madras Crocodile Bank Trust", "Arignar Anna Zoo", "rescue centre"):
            self.assertEqual(screen(gbif_row(locality=locality, **mammal), SPECIES_BY_KEY), (None, "captive_locality_text"), locality)
        for locality in ("Kaziranga National Park", "Ranthambhore safari zone 3", "Bandhavgarh Tiger Reserve"):
            self.assertIsNone(screen(gbif_row(locality=locality, **mammal), SPECIES_BY_KEY)[1], locality)

    def test_wild_birds_at_zoos_and_gardens_are_kept(self) -> None:
        bird = {"kingdom": "Animalia", "class": "Aves"}
        for locality in ("Nehru Zoological Park, Hyderabad", "Lalbagh Botanical Garden"):
            self.assertIsNone(screen(gbif_row(locality=locality, **bird), SPECIES_BY_KEY)[1], locality)
        self.assertEqual(screen(gbif_row(locality="captive aviary", **bird), SPECIES_BY_KEY)[1], "captive_locality_text")

    def test_plants_in_botanical_gardens_are_cultivated(self) -> None:
        plant = {"kingdom": "Plantae", "class": "Magnoliopsida"}
        self.assertEqual(screen(gbif_row(locality="Lalbagh Botanical Garden", **plant), SPECIES_BY_KEY)[1], "captive_locality_text")
        self.assertIsNone(screen(gbif_row(locality="Silent Valley", **plant), SPECIES_BY_KEY)[1])

    def test_ebird_records_get_assumed_moderate_precision(self) -> None:
        ebird = {"datasetKey": "4fa7b334-ce0d-4e88-aaae-2e0c138d049e", "coordinateUncertaintyInMeters": "", "issue": ""}
        record, _ = screen(gbif_row(**ebird), SPECIES_BY_KEY)
        self.assertEqual(record["coordinate_uncertainty_class"], "moderate")
        self.assertIn("uncertainty_assumed_ebird_protocol", record["quality_flags"])
        rounded, _ = screen(gbif_row(**{**ebird, "issue": "COORDINATE_ROUNDED"}), SPECIES_BY_KEY)
        self.assertEqual(rounded["coordinate_uncertainty_class"], "unknown")
        other, _ = screen(gbif_row(datasetKey="other", coordinateUncertaintyInMeters="", issue=""), SPECIES_BY_KEY)
        self.assertEqual(other["coordinate_uncertainty_class"], "unknown")

    def test_uncertainty_classes(self) -> None:
        self.assertEqual(uncertainty_class(None), "unknown")
        self.assertEqual(uncertainty_class(30), "precise")
        self.assertEqual(uncertainty_class(5000), "moderate")
        self.assertEqual(uncertainty_class(27000), "coarse")

    def test_pg_array_quotes_values(self) -> None:
        self.assertEqual(pg_array(["a", 'b"c']), '{"a","b\\"c"}')
        self.assertEqual(pg_array([]), "{}")


class SamplingTests(unittest.TestCase):
    def test_fractions_only_cap_common_species(self) -> None:
        species = [{"gbif_species_key": "1", "india_gbif_records": "144000"}, {"gbif_species_key": "2", "india_gbif_records": "500"}]
        self.assertEqual(sampling_fractions(species, 72_000), {"1": 0.5, "2": 1.0})
        self.assertEqual(sampling_fractions(species, 0), {"1": 1.0, "2": 1.0})

    def test_sample_is_reproducible_and_close_to_fraction(self) -> None:
        ids = [str(n) for n in range(20_000)]
        first = [gbif_id for gbif_id in ids if kept_in_sample(gbif_id, 0.25)]
        self.assertEqual(first, [gbif_id for gbif_id in ids if kept_in_sample(gbif_id, 0.25)])
        self.assertAlmostEqual(len(first) / len(ids), 0.25, delta=0.015)
        self.assertTrue(all(kept_in_sample(gbif_id, 1.0) for gbif_id in ids[:100]))


if __name__ == "__main__":
    unittest.main()
