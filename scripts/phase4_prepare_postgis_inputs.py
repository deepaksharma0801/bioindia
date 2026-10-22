"""Create reproducible, quality-controlled PostGIS load files from the GBIF occurrence download.

Every input record is either accepted or written to the exclusion log with a reason. Records
are not dropped for coarse coordinates; they are kept and labelled with a coordinate-uncertainty
class and quality flags so analyses can choose an appropriate precision.

Input:  data/raw/gbif/<download key>.zip and <download key>_metadata.json
Output: data/processed/species_master.json
        data/processed/occurrences_clean.jsonl
        data/analytics/occurrence_exclusions.csv
        data/analytics/data_quality_report.json
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GBIF_DIR = ROOT / "data" / "raw" / "gbif"
DOWNLOAD_KEY = "0040886-260928105237408"
SOURCE_ZIP = GBIF_DIR / f"{DOWNLOAD_KEY}.zip"
SOURCE_METADATA = GBIF_DIR / f"{DOWNLOAD_KEY}_metadata.json"
STATE_BOUNDARIES = ROOT / "data" / "raw" / "india_states_admin_current.geojson"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"

# Platform species IDs are kept stable for the existing backend and dashboard. The IUCN categories
# are a project reference list carried over from the original five-species configuration; they are
# stored as source-reported and are replaced by verified values once an IUCN export is imported.
SPECIES = {
    "Panthera tigris": {"species_id": "tiger", "common_name": "Tiger", "iucn_category": "EN"},
    "Elephas maximus": {"species_id": "elephant", "common_name": "Asian Elephant", "iucn_category": "EN"},
    "Rhinoceros unicornis": {"species_id": "rhino", "common_name": "Indian Rhinoceros", "iucn_category": "VU"},
    "Melursus ursinus": {"species_id": "bear", "common_name": "Sloth Bear", "iucn_category": "VU"},
    "Crocodylus palustris": {"species_id": "croc", "common_name": "Mugger Crocodile", "iucn_category": "VU"},
}
IUCN_STATUS_SOURCE = "Project reference list (scripts/phase4_prepare_postgis_inputs.py); not verified against an IUCN Red List import"

# GBIF issues that make a coordinate unusable.
EXCLUDING_GEOSPATIAL_ISSUES = {
    "ZERO_COORDINATE", "COORDINATE_INVALID", "COORDINATE_OUT_OF_RANGE", "COUNTRY_COORDINATE_MISMATCH",
    "PRESUMED_SWAPPED_COORDINATE", "PRESUMED_NEGATED_LATITUDE", "PRESUMED_NEGATED_LONGITUDE",
}
EXCLUDED_BASIS = {"FOSSIL_SPECIMEN", "LIVING_SPECIMEN"}
# Amur tiger is not wild in India; such records are almost certainly captive or misidentified.
NON_NATIVE_SUBSPECIES = {("Panthera tigris", "altaica")}
CAPTIVE_ESTABLISHMENT = {"managed", "captive", "cultivated"}
EARLIEST_YEAR = 1700
# Tolerance around the land boundary for coastal and estuarine records (e.g. mugger, Sunderbans).
COASTAL_TOLERANCE_M = 10_000
PRECISE_M = 1_000
MODERATE_M = 10_000


def parse_event_date(raw: str, year: str, month: str, day: str) -> tuple[date | None, str | None, str | None]:
    """Return (first date of the period, precision, exclusion reason)."""
    text = (raw or "").strip()
    if "/" in text:
        start, end = text.split("/", 1)
        if start[:4] != end[:4]:
            return None, None, "date_range_spans_years"
        text = start
    text = text.split("T")[0]
    if not text and year:
        text = "-".join(part for part in (year, month.zfill(2) if month else "", day.zfill(2) if day and month else "") if part)
    if not text:
        return None, None, "missing_date"
    try:
        if len(text) == 4:
            parsed, precision = date(int(text), 1, 1), "year"
        elif len(text) == 7:
            parsed, precision = date(int(text[:4]), int(text[5:7]), 1), "month"
        else:
            parsed, precision = date.fromisoformat(text[:10]), "day"
    except ValueError:
        return None, None, "invalid_date"
    if parsed.year < EARLIEST_YEAR or parsed > date.today():
        return None, None, "impossible_date"
    return parsed, precision, None


def uncertainty_class(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= PRECISE_M:
        return "precise"
    if value <= MODERATE_M:
        return "moderate"
    return "coarse"


def screen(row: dict[str, str]) -> tuple[dict[str, object] | None, str | None]:
    """Quality-screen one GBIF row. Returns (accepted record, None) or (None, exclusion reason)."""
    species = SPECIES.get(row.get("species", ""))
    issues = [issue for issue in (row.get("issue") or "").split(";") if issue]
    if species is None:
        return None, "unmatched_species"
    if (row.get("occurrenceStatus") or "").upper() != "PRESENT":
        return None, "occurrence_status_not_present"
    if row.get("basisOfRecord") in EXCLUDED_BASIS:
        return None, f"basis_of_record_{row['basisOfRecord'].lower()}"
    if (row["species"], row.get("infraspecificEpithet", "")) in NON_NATIVE_SUBSPECIES:
        return None, "non_native_subspecies_likely_captive"
    if (row.get("establishmentMeans") or "").lower() in CAPTIVE_ESTABLISHMENT:
        return None, "captive_or_managed"
    if not row.get("decimalLatitude") or not row.get("decimalLongitude"):
        return None, "missing_coordinates"
    excluding = sorted(EXCLUDING_GEOSPATIAL_ISSUES.intersection(issues))
    if excluding:
        return None, f"gbif_geospatial_issue_{excluding[0].lower()}"
    try:
        latitude, longitude = float(row["decimalLatitude"]), float(row["decimalLongitude"])
    except ValueError:
        return None, "invalid_coordinates"
    event_date, precision, date_reason = parse_event_date(row.get("eventDate", ""), row.get("year", ""), row.get("month", ""), row.get("day", ""))
    if date_reason:
        return None, date_reason

    uncertainty = float(row["coordinateUncertaintyInMeters"]) if row.get("coordinateUncertaintyInMeters") else None
    certainty = uncertainty_class(uncertainty)
    flags = [f"uncertainty_{certainty}", f"date_precision_{precision}"]
    if "COORDINATE_ROUNDED" in issues:
        flags.append("coordinate_rounded")
    if row.get("basisOfRecord") in {"PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "MATERIAL_CITATION"}:
        flags.append("collection_record")
    return {
        "occurrence_id": f"GBIF:{row['gbifID']}",
        "species_id": species["species_id"],
        "scientific_name_original": row.get("verbatimScientificName") or row.get("scientificName"),
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_uncertainty": uncertainty,
        "coordinate_uncertainty_class": certainty,
        "event_date": event_date.isoformat(),
        "date_precision": precision,
        "year": event_date.year,
        "month": event_date.month if precision in {"month", "day"} else None,
        "state": None,
        "basis_of_record": row.get("basisOfRecord") or None,
        "dataset_key": row["datasetKey"],
        "source": "GBIF",
        "source_record_id": row["gbifID"],
        "license": row.get("license") or None,
        "quality_flags": flags,
        "gbif_issues": issues,
        "_recorded_by": row.get("recordedBy") or "",
    }, None


def load_india():
    import geopandas as gpd

    states = gpd.read_file(STATE_BOUNDARIES).to_crs("EPSG:6933")
    tolerant = states.union_all().buffer(COASTAL_TOLERANCE_M)
    return states, tolerant


def attribute_states(records: list[dict[str, object]], excluded: list[dict[str, object]]) -> list[dict[str, object]]:
    """Drop points outside India (with a coastal tolerance) and attribute each kept point to a state."""
    import geopandas as gpd

    states, tolerant = load_india()
    points = gpd.GeoDataFrame(
        records,
        geometry=gpd.points_from_xy([r["longitude"] for r in records], [r["latitude"] for r in records]),
        crs="EPSG:4326",
    ).to_crs("EPSG:6933")
    inside = points.geometry.within(tolerant).values
    joined = gpd.sjoin_nearest(points[inside][["geometry"]], states[["state", "geometry"]], how="left", max_distance=COASTAL_TOLERANCE_M)
    nearest_state = joined[~joined.index.duplicated()]["state"]
    kept = []
    for position, record in enumerate(records):
        if not inside[position]:
            excluded.append({"source_record_id": record["source_record_id"], "species_id": record["species_id"], "reason": "coordinate_outside_india"})
            continue
        state = nearest_state.get(position)
        record["state"] = state if isinstance(state, str) else None
        kept.append(record)
    return kept


def remove_duplicates(records: list[dict[str, object]], excluded: list[dict[str, object]]) -> list[dict[str, object]]:
    """Exclude repeat uploads; flag, but keep, separate sightings that share a place and date.

    A duplicate is the same species, named observer, location (~11 m) and exact day; the record with the
    smallest stated uncertainty is kept. Records from different or unnamed observers are distinct
    sightings even when rounded coordinates coincide, so they stay with a 'shared_place_and_date' flag.
    """
    def place_date(record: dict[str, object]) -> tuple:
        return (record["species_id"], round(record["latitude"], 4), round(record["longitude"], 4), record["event_date"], record["date_precision"])

    groups: dict[tuple, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        observer = str(record.pop("_recorded_by", "") or "").strip().casefold()
        # Unnamed observers can't be matched, and a month- or year-only date can't show two
        # records are the same sighting, so those each stay a separate group.
        if not observer or record["date_precision"] != "day":
            observer = f"record:{record['source_record_id']}"
        groups[(*place_date(record), observer)].append(record)
    kept = []
    for group in groups.values():
        group.sort(key=lambda r: (r["coordinate_uncertainty"] is None, r["coordinate_uncertainty"] or 0, int(r["source_record_id"])))
        kept.append(group[0])
        for duplicate in group[1:]:
            excluded.append({"source_record_id": duplicate["source_record_id"], "species_id": duplicate["species_id"], "reason": f"duplicate_of_gbif_{group[0]['source_record_id']}"})
    shared = Counter(place_date(record) for record in kept)
    for record in kept:
        if shared[place_date(record)] > 1:
            record["quality_flags"].append("shared_place_and_date")
    return sorted(kept, key=lambda r: int(r["source_record_id"]))


def species_master(rows: list[dict[str, str]], doi: str) -> list[dict[str, object]]:
    master = {}
    for row in rows:
        species = SPECIES.get(row.get("species", ""))
        if species is None or species["species_id"] in master:
            continue
        name = row["species"]
        master[species["species_id"]] = {
            "species_id": species["species_id"],
            "scientific_name": name,
            "canonical_name": name,
            "common_name": species["common_name"],
            "kingdom": row.get("kingdom") or None, "phylum": row.get("phylum") or None,
            "class_name": row.get("class") or None, "order_name": row.get("order") or None,
            "family": row.get("family") or None, "genus": row.get("genus") or None,
            "species_epithet": name.split()[1],
            "gbif_taxon_key": int(row["speciesKey"]) if row.get("speciesKey") else None,
            "iucn_taxon_id": None, "native_status": None, "endemic_status": None, "environment_type": None,
            "current_iucn_status": species["iucn_category"],
            "current_iucn_status_source": IUCN_STATUS_SOURCE,
            "source": "GBIF Backbone Taxonomy via occurrence download",
            "source_dataset_identifier": doi,
            "license": None,
        }
    return list(master.values())


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    doi = f"https://doi.org/{metadata['doi']}"

    with zipfile.ZipFile(SOURCE_ZIP) as bundle, bundle.open(f"{DOWNLOAD_KEY}.csv") as handle:
        rows = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE))

    accepted: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for row in rows:
        record, reason = screen(row)
        if reason:
            excluded.append({"source_record_id": row.get("gbifID"), "species_id": SPECIES.get(row.get("species", ""), {}).get("species_id"), "reason": reason})
        else:
            accepted.append({**record, "source_download_doi": doi})
    accepted = attribute_states(accepted, excluded)
    accepted = remove_duplicates(accepted, excluded)

    (PROCESSED / "species_master.json").write_text(json.dumps(species_master(rows, doi), indent=2), encoding="utf-8")
    with (PROCESSED / "occurrences_clean.jsonl").open("w", encoding="utf-8") as handle:
        for record in accepted:
            handle.write(json.dumps(record) + "\n")
    with (ANALYTICS / "occurrence_exclusions.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_record_id", "species_id", "reason"])
        writer.writeheader()
        writer.writerows(excluded)

    reasons = Counter("duplicate_record" if item["reason"].startswith("duplicate_of_") else item["reason"] for item in excluded)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "GBIF.org occurrence download",
        "source_download_key": DOWNLOAD_KEY,
        "source_download_doi": doi,
        "citation": f"GBIF.org ({metadata['created'][:10]}) GBIF Occurrence Download {doi}",
        "input_records": len(rows),
        "accepted_records": len(accepted),
        "excluded_records": len(excluded),
        "exclusions_by_reason": dict(reasons.most_common()),
        "accepted_by_species": dict(Counter(r["species_id"] for r in accepted)),
        "coordinate_uncertainty_by_species": {
            species_id: dict(Counter(r["coordinate_uncertainty_class"] for r in accepted if r["species_id"] == species_id))
            for species_id in sorted({r["species_id"] for r in accepted})
        },
        "date_precision": dict(Counter(r["date_precision"] for r in accepted)),
        "records_flagged_shared_place_and_date": sum(1 for r in accepted if "shared_place_and_date" in r["quality_flags"]),
        "records_without_state": sum(1 for r in accepted if not r["state"]),
        "rules": {
            "coordinate_uncertainty_class": f"precise <= {PRECISE_M} m, moderate <= {MODERATE_M} m, coarse > {MODERATE_M} m, unknown when not stated",
            "india_screen": f"point within geoBoundaries IND ADM1 buffered by {COASTAL_TOLERANCE_M} m; state from the containing or nearest state",
            "duplicates": "same species, named observer (recordedBy), coordinates rounded to 4 decimals (~11 m) and exact day (day-precision dates only); the record with the smallest stated uncertainty is kept",
            "shared_place_and_date": "flag on kept records from different or unnamed observers that share species, rounded coordinates and date; they are separate sightings, so count unique species-place-days when needed",
            "excluded_gbif_issues": sorted(EXCLUDING_GEOSPATIAL_ISSUES),
            "excluded_basis_of_record": sorted(EXCLUDED_BASIS),
        },
        "caveats": [
            "Coarse records are usually coordinates obscured by the publisher to protect threatened species; they are kept but are unsuitable for point-level overlays.",
            "Occurrence records are observations, not population abundance; sampling effort varies over time and space.",
            "Records are licensed per dataset (CC0, CC BY, CC BY-NC); the combined dataset is CC BY-NC 4.0.",
        ],
    }
    (ANALYTICS / "data_quality_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
