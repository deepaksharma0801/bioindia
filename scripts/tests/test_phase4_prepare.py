import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase4_prepare_postgis_inputs import parse_event_date, remove_duplicates, screen, uncertainty_class


def gbif_row(**overrides):
    row = {
        "gbifID": "100", "datasetKey": "d1", "species": "Panthera tigris", "infraspecificEpithet": "tigris",
        "scientificName": "Panthera tigris tigris", "verbatimScientificName": "Panthera tigris",
        "occurrenceStatus": "PRESENT", "basisOfRecord": "HUMAN_OBSERVATION", "establishmentMeans": "",
        "decimalLatitude": "23.5", "decimalLongitude": "80.1", "coordinateUncertaintyInMeters": "25000",
        "eventDate": "2021-03-04T06:30", "year": "2021", "month": "3", "day": "4",
        "issue": "COORDINATE_ROUNDED;CONTINENT_DERIVED_FROM_COORDINATES", "license": "CC_BY_NC_4_0",
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
        record, reason = screen(gbif_row())
        self.assertIsNone(reason)
        self.assertEqual(record["occurrence_id"], "GBIF:100")
        self.assertEqual(record["species_id"], "tiger")
        self.assertEqual(record["coordinate_uncertainty_class"], "coarse")
        self.assertIn("coordinate_rounded", record["quality_flags"])
        self.assertIn("date_precision_day", record["quality_flags"])

    def test_exclusion_reasons(self) -> None:
        cases = {
            "unmatched_species": gbif_row(species="Panthera leo"),
            "occurrence_status_not_present": gbif_row(occurrenceStatus="ABSENT"),
            "basis_of_record_fossil_specimen": gbif_row(basisOfRecord="FOSSIL_SPECIMEN"),
            "non_native_subspecies_likely_captive": gbif_row(infraspecificEpithet="altaica"),
            "captive_or_managed": gbif_row(establishmentMeans="managed"),
            "missing_coordinates": gbif_row(decimalLatitude=""),
            "gbif_geospatial_issue_country_coordinate_mismatch": gbif_row(issue="COUNTRY_COORDINATE_MISMATCH"),
            "missing_date": gbif_row(eventDate="", year="", month="", day=""),
        }
        for expected, row in cases.items():
            self.assertEqual(screen(row), (None, expected), expected)

    def test_uncertainty_classes(self) -> None:
        self.assertEqual(uncertainty_class(None), "unknown")
        self.assertEqual(uncertainty_class(30), "precise")
        self.assertEqual(uncertainty_class(5000), "moderate")
        self.assertEqual(uncertainty_class(27000), "coarse")


class DuplicateTests(unittest.TestCase):
    def test_same_observer_repeat_upload_keeps_most_precise(self) -> None:
        coarse, _ = screen(gbif_row(gbifID="1", coordinateUncertaintyInMeters="25000", recordedBy="Asha R"))
        precise, _ = screen(gbif_row(gbifID="2", coordinateUncertaintyInMeters="50", recordedBy="asha r"))
        other_day, _ = screen(gbif_row(gbifID="3", eventDate="2021-03-05", recordedBy="Asha R"))
        excluded = []
        kept = remove_duplicates([coarse, precise, other_day], excluded)
        self.assertEqual([r["source_record_id"] for r in kept], ["2", "3"])
        self.assertEqual(excluded, [{"source_record_id": "1", "species_id": "tiger", "reason": "duplicate_of_gbif_2"}])
        self.assertNotIn("shared_place_and_date", kept[0]["quality_flags"])

    def test_different_or_unnamed_observers_are_kept_and_flagged(self) -> None:
        first, _ = screen(gbif_row(gbifID="1", recordedBy="Asha R"))
        second, _ = screen(gbif_row(gbifID="2", recordedBy="Vikram S"))
        unnamed, _ = screen(gbif_row(gbifID="3", recordedBy=""))
        excluded = []
        kept = remove_duplicates([first, second, unnamed], excluded)
        self.assertEqual(excluded, [])
        self.assertEqual(len(kept), 3)
        self.assertTrue(all("shared_place_and_date" in r["quality_flags"] for r in kept))
        self.assertTrue(all("_recorded_by" not in r for r in kept))


if __name__ == "__main__":
    unittest.main()
