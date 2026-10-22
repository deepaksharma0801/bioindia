from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
SOURCE_DIR = PROJECT_ROOT / "extinct-species-since-1500" / "data"

PROCESSED_OCCURRENCES = [
    DATA_DIR / "processed" / "occurrences_raw.csv",
    DATA_DIR / "occurrences_raw.csv",
]

OUTPUT_PATH = PROCESSED_DIR / "occurrence_points.json"
MAX_GROUPED_POINTS_PER_SPECIES = 500


@dataclass(frozen=True)
class SpeciesConfig:
    identifier: str
    name: str
    scientific_name: str
    status: str
    color: str
    emoji: str
    source_files: tuple[str, ...]


SPECIES_CONFIGS = [
    SpeciesConfig(
        identifier="tiger",
        name="Bengal Tiger",
        scientific_name="Panthera tigris",
        status="EN",
        color="#ff6030",
        emoji="\U0001F42F",
        source_files=("tiger_india_gbif.xls", "Panthera_tigris_Linnaeus,_1758_India.xls"),
    ),
    SpeciesConfig(
        identifier="elephant",
        name="Asian Elephant",
        scientific_name="Elephas maximus",
        status="EN",
        color="#6090d0",
        emoji="\U0001F418",
        source_files=("Elephas_maximus_Linnaeus,_1758_India.xls",),
    ),
    SpeciesConfig(
        identifier="rhino",
        name="Indian Rhinoceros",
        scientific_name="Rhinoceros unicornis",
        status="VU",
        color="#4abaa8",
        emoji="\U0001F98F",
        source_files=("Rhinoceros_unicornis_Linnaeus,_1758_India.xls",),
    ),
    SpeciesConfig(
        identifier="bear",
        name="Sloth Bear",
        scientific_name="Melursus ursinus",
        status="VU",
        color="#c07830",
        emoji="\U0001F43B",
        source_files=("Melursus_ursinus_Shaw,_1791_India.xls",),
    ),
    SpeciesConfig(
        identifier="croc",
        name="Mugger Crocodile",
        scientific_name="Crocodylus palustris",
        status="VU",
        color="#30a080",
        emoji="\U0001F40A",
        source_files=("Crocodylus_palustris_Lesson,_1831_India.xls",),
    ),
]


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def within_india_bounds(lat: float, lng: float) -> bool:
    return 6.0 <= lat <= 38.5 and 67.0 <= lng <= 98.5


def detect_csv_like(path: Path) -> bool:
    header = path.read_bytes()[:32]
    if header.startswith(b"PK"):
        return False
    prefix = header.decode("utf-8", errors="ignore").lower()
    return prefix.startswith("scientificname") or prefix.startswith("key,")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def scientific_name_matches(candidate: str | None, expected: str) -> bool:
    if not candidate:
        return False
    normalized = candidate.lower()
    return expected.lower() in normalized


def normalized_state(row: dict[str, str]) -> str:
    return (
        clean_text(row.get("stateProvince"))
        or clean_text(row.get("state"))
        or "India"
    )


def normalized_year(row: dict[str, str]) -> int | None:
    year = parse_int(row.get("year"))
    if year:
        return year
    event_date = clean_text(row.get("eventDate"))
    if event_date and len(event_date) >= 4:
        try:
            return int(event_date[:4])
        except ValueError:
            return None
    return None


def build_point_rows_from_csv(source_rows: Iterable[dict[str, str]], config: SpeciesConfig) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for row in source_rows:
        scientific_name = clean_text(row.get("scientificName")) or config.scientific_name
        if "scientificName" in row and not scientific_name_matches(scientific_name, config.scientific_name):
            continue

        lat = parse_float(row.get("decimalLatitude") or row.get("latitude"))
        lng = parse_float(row.get("decimalLongitude") or row.get("longitude"))
        if lat is None or lng is None or not within_india_bounds(lat, lng):
            continue

        points.append(
            {
                "scientificName": scientific_name,
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "state": normalized_state(row),
                "year": normalized_year(row),
                "eventDate": clean_text(row.get("eventDate")),
                "basisOfRecord": clean_text(row.get("basisOfRecord")) or "OBSERVATION",
                "habitat": clean_text(row.get("habitat")) or clean_text(row.get("locality")) or "Unknown habitat",
                "individualCount": parse_int(row.get("individualCount")) or 1,
                "iucnCategory": clean_text(row.get("iucnCategory")) or clean_text(row.get("iucnRedListCategory")) or config.status,
                "sourceRecordId": clean_text(row.get("gbifID")) or clean_text(row.get("key")),
            }
        )
    return points


def choose_best_local_file(config: SpeciesConfig) -> Path | None:
    for file_name in config.source_files:
        candidate = SOURCE_DIR / file_name
        if candidate.exists():
            return candidate
    return None


def load_points_for_species(config: SpeciesConfig) -> tuple[list[dict[str, object]], str]:
    processed_path = next((path for path in PROCESSED_OCCURRENCES if path.exists()), None)
    if processed_path:
        rows = read_csv_rows(processed_path)
        return build_point_rows_from_csv(rows, config), processed_path.name

    local_path = choose_best_local_file(config)
    if local_path is None:
        return [], "missing"

    if detect_csv_like(local_path):
        rows = read_csv_rows(local_path)
        return build_point_rows_from_csv(rows, config), local_path.name

    return [], local_path.name


def group_points(points: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[float, float, int | None], dict[str, object]] = {}

    for point in points:
        key = (round(float(point["lat"]), 3), round(float(point["lng"]), 3), point.get("year"))
        bucket = grouped.get(key)
        if bucket is None:
            grouped[key] = {
                "lat": key[0],
                "lng": key[1],
                "year": point.get("year"),
                "state": point.get("state") or "India",
                "obs": 1,
                "individualCountTotal": int(point.get("individualCount") or 1),
                "eventDate": point.get("eventDate"),
                "basisOfRecord": point.get("basisOfRecord"),
                "habitat": point.get("habitat"),
                "iucnCategory": point.get("iucnCategory"),
            }
            continue

        bucket["obs"] = int(bucket["obs"]) + 1
        bucket["individualCountTotal"] = int(bucket["individualCountTotal"]) + int(point.get("individualCount") or 1)
        if not bucket.get("state") and point.get("state"):
            bucket["state"] = point.get("state")
        if not bucket.get("habitat") and point.get("habitat"):
            bucket["habitat"] = point.get("habitat")
        if not bucket.get("eventDate") and point.get("eventDate"):
            bucket["eventDate"] = point.get("eventDate")

    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            int(item.get("obs") or 0),
            int(item.get("year") or 0),
            int(item.get("individualCountTotal") or 0),
        ),
        reverse=True,
    )
    return ordered[:MAX_GROUPED_POINTS_PER_SPECIES]


def export_payload() -> dict[str, object]:
    species_payload = []
    source_mode = "local_species_exports"

    for config in SPECIES_CONFIGS:
        raw_points, source_name = load_points_for_species(config)
        if source_name == "occurrences_raw.csv":
            source_mode = "processed_occurrences_raw"
        grouped_points = group_points(raw_points)
        species_payload.append(
            {
                "id": config.identifier,
                "name": config.name,
                "scientificName": config.scientific_name,
                "status": config.status,
                "col": config.color,
                "emoji": config.emoji,
                "sourceFile": source_name,
                "totalRawRecords": len(raw_points),
                "groupedPointCount": len(grouped_points),
                "points": grouped_points,
            }
        )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceMode": source_mode,
        "species": species_payload,
    }


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    payload = export_payload()
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Wrote {OUTPUT_PATH}")
    for species in payload["species"]:
        print(
            f"  - {species['name']}: {species['totalRawRecords']} raw records -> "
            f"{species['groupedPointCount']} grouped points from {species['sourceFile']}"
        )


if __name__ == "__main__":
    main()
