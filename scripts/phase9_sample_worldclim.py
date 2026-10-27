"""Sample WorldClim 2.1 climate normals at quality-controlled occurrence coordinates in PostGIS.

Only records with stated coordinate uncertainty of at most 10 km are sampled (coarser points can
fall in a different 10-arc-minute cell from the true location). The global 10' rasters are small,
so they are read into memory and every point is looked up with array indexing.

Output: data/analytics/species_climate_profiles.json   (per-species mean, 10th and 90th percentile)
        data/analytics/climate_sampling_report.json
"""

from __future__ import annotations

import json
import os
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import psycopg
import rasterio
from rasterio.transform import rowcol


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "worldclim"
ANALYTICS = ROOT / "data" / "analytics"
EXTRACTED = RAW / "extracted_10m"
BIO_ARCHIVE = RAW / "wc2.1_10m_bio.zip"
ELEVATION_ARCHIVE = RAW / "wc2.1_10m_elev.zip"
PROFILE_OUTPUT = ANALYTICS / "species_climate_profiles.json"
REPORT_OUTPUT = ANALYTICS / "climate_sampling_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
ELIGIBLE_UNCERTAINTY_CLASSES = ["precise", "moderate"]

RASTERS = {
    "annual_mean_temperature_c": (BIO_ARCHIVE, "wc2.1_10m_bio_1.tif"),
    "temperature_seasonality_sd_x100": (BIO_ARCHIVE, "wc2.1_10m_bio_4.tif"),
    "annual_precipitation_mm": (BIO_ARCHIVE, "wc2.1_10m_bio_12.tif"),
    "precipitation_seasonality_cv": (BIO_ARCHIVE, "wc2.1_10m_bio_15.tif"),
    "elevation_m": (ELEVATION_ARCHIVE, "wc2.1_10m_elev.tif"),
}


def extract_required_rasters() -> dict[str, Path]:
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, (archive, filename) in RASTERS.items():
        destination = EXTRACTED / filename
        if not destination.exists():
            with zipfile.ZipFile(archive) as bundle, bundle.open(filename) as source, destination.open("wb") as target:
                target.write(source.read())
        paths[name] = destination
    return paths


def load_raster(path: Path):
    with rasterio.open(path) as dataset:
        band = dataset.read(1, masked=True)
        return band.astype("float64").filled(np.nan), dataset.transform


def sample(array: np.ndarray, transform, longitude: np.ndarray, latitude: np.ndarray) -> np.ndarray:
    rows, cols = rowcol(transform, longitude, latitude)
    rows, cols = np.asarray(rows), np.asarray(cols)
    inside = (rows >= 0) & (rows < array.shape[0]) & (cols >= 0) & (cols < array.shape[1])
    values = np.full(len(longitude), np.nan)
    values[inside] = array[rows[inside], cols[inside]]
    return values


def main() -> None:
    paths = extract_required_rasters()
    rasters = {name: load_raster(path) for name, path in paths.items()}
    with psycopg.connect(DATABASE_URL) as connection:
        points = connection.execute(
            "SELECT species_id, longitude, latitude FROM occurrences WHERE coordinate_uncertainty_class = ANY(%s)",
            (ELIGIBLE_UNCERTAINTY_CLASSES,),
        ).fetchall()
        left_out_rows = connection.execute(
            """SELECT species_id, COALESCE(coordinate_uncertainty_class, 'unknown'), COUNT(*) FROM occurrences
               WHERE NOT (coordinate_uncertainty_class = ANY(%s)) OR coordinate_uncertainty_class IS NULL GROUP BY 1, 2""",
            (ELIGIBLE_UNCERTAINTY_CLASSES,),
        ).fetchall()
    left_out: dict[str, dict[str, int]] = defaultdict(dict)
    for species_id, certainty, count in left_out_rows:
        left_out[species_id][certainty] = count

    species = np.array([row[0] for row in points])
    longitude = np.array([row[1] for row in points], dtype="float64")
    latitude = np.array([row[2] for row in points], dtype="float64")
    values = {name: sample(array, transform, longitude, latitude) for name, (array, transform) in rasters.items()}
    complete = ~np.isnan(np.column_stack([values[name] for name in RASTERS])).any(axis=1) if len(points) else np.array([], dtype=bool)

    profiles = []
    for species_id in sorted(set(species.tolist())):
        mask = (species == species_id) & complete
        if not mask.any():
            continue
        profile = {"species_id": species_id, "sampled_occurrence_count": int(mask.sum()), "records_left_out": left_out.get(species_id, {})}
        for name in RASTERS:
            column = values[name][mask]
            profile[name] = round(float(column.mean()), 4)
            profile[f"{name}_p10"] = round(float(np.percentile(column, 10)), 4)
            profile[f"{name}_p90"] = round(float(np.percentile(column, 90)), 4)
        profiles.append(profile)

    metadata = {
        "source": "WorldClim version 2.1 historical climate normals and elevation",
        "reference_period": "1970-2000",
        "spatial_resolution": "10 arc-minutes",
        "coordinate_reference_system": "WGS 84 longitude/latitude",
        "method": "Point sampling at quality-controlled occurrence coordinates with stated uncertainty of at most 10 km; per species mean and 10th/90th percentiles.",
        "records_left_out_rule": "records with coarse (> 10 km) or unstated coordinate uncertainty are not sampled; counts per species are in records_left_out.",
        "limitations": "These are baseline climate and elevation associations at observed locations, not climate-change exposure, habitat suitability, or causal risk estimates. Each record counts once, so heavily recorded places weigh more.",
    }
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    PROFILE_OUTPUT.write_text(json.dumps({"metadata": metadata, "profiles": profiles}, indent=2), encoding="utf-8")
    report = {"eligible_occurrences": len(points), "complete_climate_samples": int(complete.sum()), "species_profiles": len(profiles),
              "raster_files": {name: path.name for name, path in paths.items()}}
    REPORT_OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
