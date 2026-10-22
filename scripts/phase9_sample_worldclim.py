"""Sample real WorldClim 2.1 climate normals at accepted occurrence coordinates."""

from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

import numpy as np
import rasterio


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "worldclim"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
EXTRACTED = RAW / "extracted_10m"
BIO_ARCHIVE = RAW / "wc2.1_10m_bio.zip"
ELEVATION_ARCHIVE = RAW / "wc2.1_10m_elev.zip"
INPUT = PROCESSED / "occurrences_clean.jsonl"
POINT_OUTPUT = ANALYTICS / "occurrence_climate.jsonl"
PROFILE_OUTPUT = ANALYTICS / "species_climate_profiles.json"
REPORT_OUTPUT = ANALYTICS / "climate_sampling_report.json"

# Same precision rule as the protected-area overlay: coarser points (often deliberately obscured)
# can fall in a different 10-arc-minute climate cell from the true location.
ELIGIBLE_UNCERTAINTY_CLASSES = {"precise", "moderate"}

RASTERS = {
    "annual_mean_temperature_c": (BIO_ARCHIVE, "wc2.1_10m_bio_1.tif", 1.0),
    "temperature_seasonality_sd_x100": (BIO_ARCHIVE, "wc2.1_10m_bio_4.tif", 1.0),
    "annual_precipitation_mm": (BIO_ARCHIVE, "wc2.1_10m_bio_12.tif", 1.0),
    "precipitation_seasonality_cv": (BIO_ARCHIVE, "wc2.1_10m_bio_15.tif", 1.0),
    "elevation_m": (ELEVATION_ARCHIVE, "wc2.1_10m_elev.tif", 1.0),
}


def extract_required_rasters() -> dict[str, Path]:
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for _, (archive, filename, _) in RASTERS.items():
        destination = EXTRACTED / filename
        if not destination.exists():
            with zipfile.ZipFile(archive) as bundle:
                with bundle.open(filename) as source, destination.open("wb") as target:
                    target.write(source.read())
        paths[filename] = destination
    return paths


def sample_value(dataset: rasterio.io.DatasetReader, longitude: float, latitude: float) -> float | None:
    value = next(dataset.sample([(longitude, latitude)], masked=True))[0]
    if np.ma.is_masked(value):
        return None
    return float(value)


def main() -> None:
    if not INPUT.exists():
        raise SystemExit(f"Missing cleaned occurrence input: {INPUT}")
    paths = extract_required_rasters()
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    datasets = {
        name: rasterio.open(paths[filename])
        for name, (_, filename, _) in RASTERS.items()
    }
    samples_by_species: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    input_rows = 0
    complete_samples = 0
    left_out: dict[str, Counter] = defaultdict(Counter)
    try:
        with INPUT.open(encoding="utf-8") as source, POINT_OUTPUT.open("w", encoding="utf-8") as target:
            for line in source:
                if not line.strip():
                    continue
                input_rows += 1
                occurrence = json.loads(line)
                if occurrence.get("coordinate_uncertainty_class") not in ELIGIBLE_UNCERTAINTY_CLASSES:
                    left_out[occurrence["species_id"]][occurrence.get("coordinate_uncertainty_class") or "unknown"] += 1
                    continue
                longitude = float(occurrence["longitude"])
                latitude = float(occurrence["latitude"])
                values: dict[str, float | None] = {}
                for name, (_, _, scale) in RASTERS.items():
                    raw_value = sample_value(datasets[name], longitude, latitude)
                    values[name] = round(raw_value * scale, 4) if raw_value is not None else None
                if all(value is not None for value in values.values()):
                    complete_samples += 1
                    for name, value in values.items():
                        samples_by_species[occurrence["species_id"]][name].append(float(value))
                target.write(json.dumps({"occurrence_id": occurrence["occurrence_id"], "species_id": occurrence["species_id"], **values}) + "\n")
    finally:
        for dataset in datasets.values():
            dataset.close()

    profiles = [
        {
            "species_id": species_id,
            "sampled_occurrence_count": len(values["annual_mean_temperature_c"]),
            "records_left_out": dict(left_out.get(species_id, {})),
            **{name: round(fmean(measurements), 4) for name, measurements in values.items() if measurements},
        }
        for species_id, values in sorted(samples_by_species.items())
    ]
    metadata = {
        "source": "WorldClim version 2.1 historical climate normals and elevation",
        "reference_period": "1970-2000",
        "spatial_resolution": "10 arc-minutes",
        "coordinate_reference_system": "WGS 84 longitude/latitude",
        "method": "Point sampling at quality-controlled occurrence coordinates with stated uncertainty of at most 10 km, followed by arithmetic mean by species.",
        "records_left_out_rule": "records with coarse (> 10 km) or unstated coordinate uncertainty are not sampled; counts per species are in records_left_out.",
        "limitations": "These are baseline climate and elevation associations at observed locations, not climate-change exposure, habitat suitability, or causal risk estimates.",
    }
    PROFILE_OUTPUT.write_text(json.dumps({"metadata": metadata, "profiles": profiles}, indent=2), encoding="utf-8")
    REPORT_OUTPUT.write_text(json.dumps({"input_occurrences": input_rows, "complete_climate_samples": complete_samples, "species_profiles": len(profiles), "raster_files": {name: path.name for name, path in paths.items()}}, indent=2), encoding="utf-8")
    print(f"Sampled {complete_samples} of {input_rows} occurrences across {len(profiles)} species.")


if __name__ == "__main__":
    main()
