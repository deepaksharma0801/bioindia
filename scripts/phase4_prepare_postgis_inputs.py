"""Stream the GBIF occurrence download through record-level quality rules into a PostGIS load file.

Every input record is either written to the load file or to the exclusion log with a reason.
Records are not dropped for coarse coordinates; they keep a coordinate-uncertainty class and
quality flags so analyses can choose an appropriate precision. Spatial rules (outside India,
inside a mapped zoo, state attribution) and duplicate removal run in PostGIS during loading
(phase4_load_postgis.py), so millions of records never have to sit in memory.

Input:  data/processed/species_list.csv (phase2_build_species_list.py)
        data/raw/gbif/<download key>.zip and <download key>_metadata.json
Output: data/processed/species_master.json
        data/processed/occurrences_screened.csv     (COPY-ready)
        data/analytics/occurrence_exclusions.csv    (record-level exclusions)
        data/analytics/screening_report.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GBIF_DIR = ROOT / "data" / "raw" / "gbif"
DEFAULT_DOWNLOAD_KEY = "0006542-261023074918325"
SPECIES_LIST = ROOT / "data" / "processed" / "species_list.csv"
IUCN_DIR = ROOT / "0433e6f8-919d-4ab4-ba8a-6bc57065b07b"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
SCREENED = PROCESSED / "occurrences_screened.csv"

# Flagship common names and IUCN categories are a project reference list (the IUCN export does not
# cover them); they are stored as source-reported until a verified IUCN import replaces them.
FLAGSHIP_REFERENCE = {
    "tiger": {"common_name": "Tiger", "iucn_category": "EN"},
    "elephant": {"common_name": "Asian Elephant", "iucn_category": "EN"},
    "rhino": {"common_name": "Indian Rhinoceros", "iucn_category": "VU"},
    "bear": {"common_name": "Sloth Bear", "iucn_category": "VU"},
    "croc": {"common_name": "Mugger Crocodile", "iucn_category": "VU"},
}
IUCN_STATUS_SOURCE = "Project reference list (scripts/phase4_prepare_postgis_inputs.py); not verified against an IUCN Red List import"
IUCN_EXPORT_STATUS_SOURCE = "IUCN Red List export in project folder (global assessment); see conservation_assessments for provenance"

# GBIF issues that make a coordinate unusable.
EXCLUDING_GEOSPATIAL_ISSUES = {
    "ZERO_COORDINATE", "COORDINATE_INVALID", "COORDINATE_OUT_OF_RANGE", "COUNTRY_COORDINATE_MISMATCH",
    "PRESUMED_SWAPPED_COORDINATE", "PRESUMED_NEGATED_LATITUDE", "PRESUMED_NEGATED_LONGITUDE",
}
EXCLUDED_BASIS = {"FOSSIL_SPECIMEN", "LIVING_SPECIMEN"}
# Amur tiger is not wild in India; such records are almost certainly captive or misidentified.
NON_NATIVE_SUBSPECIES = {("Panthera tigris", "altaica")}
CAPTIVE_ESTABLISHMENT = {"managed", "captive", "cultivated"}
# Locality text that marks a captive or cultivated setting, by group. 'Safari' and 'park' alone are
# not used: they also describe wild national parks. Birds are only excluded for explicit captivity:
# free-flying birds at zoos and botanical gardens (popular birding sites) are wild records.
CAPTIVE_ANY = re.compile(r"\bcaptiv", re.IGNORECASE)
CAPTIVE_ANIMAL_LOCALITY = re.compile(
    r"\bzoo\b|zoological|rescue cent|rehabilitation cent|breeding cent|deer park|biological park|"
    r"animal park|crocodile bank|crocodile park|snake park",
    re.IGNORECASE,
)
CULTIVATED_PLANT_LOCALITY = re.compile(r"botanical garden|botanic garden|herbarium garden|\bzoo\b|zoological", re.IGNORECASE)


def captive_locality(row: dict[str, str]) -> bool:
    locality = row.get("locality") or ""
    if CAPTIVE_ANY.search(locality):
        return True
    if (row.get("kingdom") or "") == "Plantae":
        return bool(CULTIVATED_PLANT_LOCALITY.search(locality))
    if (row.get("class") or "") == "Aves":
        return False
    return bool(CAPTIVE_ANIMAL_LOCALITY.search(locality))
# Very common species (mostly eBird birds) are capped by a reproducible random sample. Each record is
# kept with probability cap / India record count, decided by a hash of its GBIF ID, so the sample is
# proportional across places and years and identical on every run. Species under the cap keep everything.
DEFAULT_CAP_PER_SPECIES = 72_000
SAMPLE_SEED = "bioindia-2026"
# eBird (EOD) never publishes coordinate uncertainty. Its records are checklist locations, not
# obscured points (eBird withholds sensitive species instead of blurring them), and its protocol
# keeps checklists under ~8 km, so unrounded eBird records are classed 'moderate' (<= 10 km) with a
# flag marking the class as assumed.
EBIRD_DATASET_KEY = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"
EARLIEST_YEAR = 1700
PRECISE_M = 1_000
MODERATE_M = 10_000

SCREENED_COLUMNS = [
    "occurrence_id", "species_id", "scientific_name_original", "latitude", "longitude", "coordinate_uncertainty",
    "coordinate_uncertainty_class", "event_date", "date_precision", "year", "month", "basis_of_record", "dataset_key",
    "source", "source_record_id", "license", "quality_flags", "gbif_issues", "source_download_doi", "recorded_by",
]
USED_COLUMNS = {
    "gbifID", "datasetKey", "speciesKey", "species", "infraspecificEpithet", "verbatimScientificName", "scientificName",
    "occurrenceStatus", "basisOfRecord", "establishmentMeans", "decimalLatitude", "decimalLongitude",
    "coordinateUncertaintyInMeters", "eventDate", "year", "month", "day", "issue", "license", "recordedBy", "locality",
    "kingdom", "phylum", "class", "order", "family", "genus",
}


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


def screen(row: dict[str, str], species_by_key: dict[str, str]) -> tuple[dict[str, object] | None, str | None]:
    """Quality-screen one GBIF row. Returns (accepted record, None) or (None, exclusion reason)."""
    species_id = species_by_key.get(row.get("speciesKey") or "")
    issues = [issue for issue in (row.get("issue") or "").split(";") if issue]
    if species_id is None:
        return None, "unmatched_species"
    if (row.get("occurrenceStatus") or "").upper() != "PRESENT":
        return None, "occurrence_status_not_present"
    if row.get("basisOfRecord") in EXCLUDED_BASIS:
        return None, f"basis_of_record_{row['basisOfRecord'].lower()}"
    if (row.get("species"), row.get("infraspecificEpithet", "")) in NON_NATIVE_SUBSPECIES:
        return None, "non_native_subspecies_likely_captive"
    if (row.get("establishmentMeans") or "").lower() in CAPTIVE_ESTABLISHMENT:
        return None, "captive_or_managed"
    if captive_locality(row):
        return None, "captive_locality_text"
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
    if uncertainty is None and row.get("datasetKey") == EBIRD_DATASET_KEY and "COORDINATE_ROUNDED" not in issues:
        certainty = "moderate"
        flags = ["uncertainty_assumed_ebird_protocol", f"date_precision_{precision}"]
    if "COORDINATE_ROUNDED" in issues:
        flags.append("coordinate_rounded")
    if row.get("basisOfRecord") in {"PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "MATERIAL_CITATION"}:
        flags.append("collection_record")
    return {
        "occurrence_id": f"GBIF:{row['gbifID']}",
        "species_id": species_id,
        "scientific_name_original": row.get("verbatimScientificName") or row.get("scientificName"),
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_uncertainty": uncertainty,
        "coordinate_uncertainty_class": certainty,
        "event_date": event_date.isoformat(),
        "date_precision": precision,
        "year": event_date.year,
        "month": event_date.month if precision in {"month", "day"} else None,
        "basis_of_record": row.get("basisOfRecord") or None,
        "dataset_key": row["datasetKey"],
        "source": "GBIF",
        "source_record_id": row["gbifID"],
        "license": row.get("license") or None,
        "quality_flags": flags,
        "gbif_issues": issues,
        "recorded_by": (row.get("recordedBy") or "").strip(),
    }, None


def sampling_fractions(species: list[dict[str, str]], cap: int | None) -> dict[str, float]:
    """Keep-probability per GBIF species key: 1.0 under the cap, cap / India record count above it."""
    fractions = {}
    for item in species:
        count = int(item["india_gbif_records"] or 0)
        fractions[item["gbif_species_key"]] = 1.0 if not cap or count <= cap else cap / count
    return fractions


def kept_in_sample(gbif_id: str, fraction: float) -> bool:
    if fraction >= 1.0:
        return True
    digest = hashlib.sha256(f"{SAMPLE_SEED}:{gbif_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < fraction


def pg_array(values: list[str]) -> str:
    return "{" + ",".join('"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' for value in values) + "}"


def load_species() -> list[dict[str, str]]:
    with SPECIES_LIST.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def iucn_common_names() -> dict[str, str]:
    names = {}
    with (IUCN_DIR / "common_names.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["language"] == "English" and (row["main"] == "true" or row["internalTaxonId"] not in names):
                names[row["internalTaxonId"]] = row["name"]
    return names


def iucn_taxonomy_by_taxon() -> dict[str, dict[str, str]]:
    with (IUCN_DIR / "taxonomy.csv").open(encoding="utf-8") as handle:
        return {
            row["internalTaxonId"]: {
                "kingdom": row["kingdomName"].title(), "phylum": row["phylumName"].title(), "class": row["className"].title(),
                "order": row["orderName"].title(), "family": row["familyName"].title(), "genus": row["genusName"],
            }
            for row in csv.DictReader(handle)
        }


def species_master(species: list[dict[str, str]], taxonomy: dict[str, dict[str, str]], doi: str) -> list[dict[str, object]]:
    """GBIF Backbone taxonomy first; IUCN taxonomy fills gaps (GBIF gives ray-finned fishes no class,
    and species without India records get no taxonomy from the download)."""
    common = iucn_common_names()
    iucn = iucn_taxonomy_by_taxon()
    master = []
    for item in species:
        flagship = FLAGSHIP_REFERENCE.get(item["species_id"])
        fallback = iucn.get(item["iucn_taxon_id"], {})
        gbif = {rank: taxonomy.get(item["gbif_species_key"], {}).get(rank) or fallback.get(rank)
                for rank in ("kingdom", "phylum", "class", "order", "family", "genus")}
        name = item["scientific_name"]
        master.append({
            "species_id": item["species_id"],
            "scientific_name": name,
            "canonical_name": item["gbif_accepted_name"] or name,
            "common_name": (flagship or {}).get("common_name") or common.get(item["iucn_taxon_id"]),
            "kingdom": gbif.get("kingdom") or item["kingdom"], "phylum": gbif.get("phylum"),
            "class_name": gbif.get("class"), "order_name": gbif.get("order"),
            "family": gbif.get("family"), "genus": gbif.get("genus") or name.split()[0],
            "species_epithet": name.split()[1],
            "gbif_taxon_key": int(item["gbif_species_key"]),
            "iucn_taxon_id": item["iucn_taxon_id"] or None,
            "native_status": "native" if item["iucn_taxon_id"] else None,
            "endemic_status": None, "environment_type": None,
            "current_iucn_status": (flagship or {}).get("iucn_category") or item["iucn_category_in_export"] or None,
            "current_iucn_status_source": IUCN_STATUS_SOURCE if flagship and not item["iucn_category_in_export"] else IUCN_EXPORT_STATUS_SOURCE,
            "source": "GBIF Backbone Taxonomy via occurrence download; species list from IUCN export",
            "source_dataset_identifier": doi,
            "license": None,
        })
    return master


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--download-key", default=DEFAULT_DOWNLOAD_KEY)
    parser.add_argument("--cap-per-species", type=int, default=DEFAULT_CAP_PER_SPECIES,
                        help="Sample very common species down to about this many records; 0 keeps everything.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_zip = GBIF_DIR / f"{args.download_key}.zip"
    metadata = json.loads((GBIF_DIR / f"{args.download_key}_metadata.json").read_text(encoding="utf-8"))
    doi = f"https://doi.org/{metadata['doi']}"
    species = load_species()
    species_by_key = {item["gbif_species_key"]: item["species_id"] for item in species}
    fractions = sampling_fractions(species, args.cap_per_species)
    sampled_out: Counter = Counter()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(sys.maxsize if sys.maxsize < 2**31 else 2**31 - 1)
    reasons: Counter = Counter()
    accepted_by_species: Counter = Counter()
    uncertainty_by_species: dict[str, Counter] = defaultdict(Counter)
    precision: Counter = Counter()
    taxonomy: dict[str, dict[str, str]] = {}
    total = 0

    with zipfile.ZipFile(source_zip) as bundle, bundle.open(f"{args.download_key}.csv") as raw, \
            SCREENED.open("w", encoding="utf-8", newline="") as screened_handle, \
            (ANALYTICS / "occurrence_exclusions.csv").open("w", encoding="utf-8", newline="") as excluded_handle:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        screened = csv.writer(screened_handle)
        excluded = csv.writer(excluded_handle)
        excluded.writerow(["source_record_id", "species_id", "reason"])
        for row in reader:
            total += 1
            key = row.get("speciesKey") or ""
            if key in species_by_key and key not in taxonomy:
                taxonomy[key] = {column: row.get(column) for column in ("kingdom", "phylum", "class", "order", "family", "genus")}
            # Sampled-out records are counted per species in the report, not written one by one to the exclusion log.
            if not kept_in_sample(row.get("gbifID") or "", fractions.get(key, 1.0)):
                sampled_out[species_by_key[key]] += 1
                continue
            record, reason = screen(row, species_by_key)
            if reason:
                reasons[reason] += 1
                excluded.writerow([row.get("gbifID"), species_by_key.get(key), reason])
                continue
            record["source_download_doi"] = doi
            record["quality_flags"] = pg_array(record["quality_flags"])
            record["gbif_issues"] = pg_array(record["gbif_issues"])
            screened.writerow(["" if record[column] is None else record[column] for column in SCREENED_COLUMNS])
            accepted_by_species[record["species_id"]] += 1
            uncertainty_by_species[record["species_id"]][record["coordinate_uncertainty_class"]] += 1
            precision[record["date_precision"]] += 1
            if total % 500_000 == 0:
                print(f"  {total:,} records screened", flush=True)

    (PROCESSED / "species_master.json").write_text(json.dumps(species_master(species, taxonomy, doi), indent=2), encoding="utf-8")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "GBIF.org occurrence download",
        "source_download_key": args.download_key,
        "source_download_doi": doi,
        "citation": f"GBIF.org ({metadata['created'][:10]}) GBIF Occurrence Download {doi}",
        "input_records": total,
        "sampling": {
            "cap_per_species": args.cap_per_species or None,
            "method": "each record kept with probability cap / India record count (hash of GBIF ID with a fixed seed): proportional across places and years, reproducible",
            "seed": SAMPLE_SEED,
            "records_sampled_out": sum(sampled_out.values()),
            "species_sampled": {
                species_id: {"kept_fraction": round(fractions[key], 4), "records_sampled_out": sampled_out[species_id]}
                for key, species_id in species_by_key.items() if fractions.get(key, 1.0) < 1.0
            },
            "note": "Divide a sampled species' record counts by kept_fraction to estimate full-download counts.",
        },
        "passed_record_level_screen": sum(accepted_by_species.values()),
        "excluded_at_record_level": sum(reasons.values()),
        "exclusions_by_reason": dict(reasons.most_common()),
        "species_with_records": len(accepted_by_species),
        "coordinate_uncertainty_by_species": {key: dict(value) for key, value in sorted(uncertainty_by_species.items())},
        "date_precision": dict(precision),
        "next_step": "phase4_load_postgis.py applies the spatial rules (outside India, mapped zoos, state attribution) and duplicate removal",
        "rules": {
            "coordinate_uncertainty_class": f"precise <= {PRECISE_M} m, moderate <= {MODERATE_M} m, coarse > {MODERATE_M} m, unknown when not stated",
            "captive_locality_text": {
                "any_group": CAPTIVE_ANY.pattern,
                "animals_except_birds": CAPTIVE_ANIMAL_LOCALITY.pattern,
                "plants": CULTIVATED_PLANT_LOCALITY.pattern,
                "birds": "only explicit captivity; free-flying birds at zoos and gardens are wild records",
            },
            "excluded_gbif_issues": sorted(EXCLUDING_GEOSPATIAL_ISSUES),
            "excluded_basis_of_record": sorted(EXCLUDED_BASIS),
        },
    }
    (ANALYTICS / "screening_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "coordinate_uncertainty_by_species"}, indent=2))


if __name__ == "__main__":
    main()
