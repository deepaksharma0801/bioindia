from __future__ import annotations

import json
from pathlib import Path

from ..config import DATASET_STATUS_FILE, DATA_DIR, OUTPUTS_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR, SCRIPTS_DIR


RAW_FILES = {
    "worldclim_bioclim": RAW_DATA_DIR / "worldclim" / "wc2.1_10m_bio.zip",
    "worldclim_elevation": RAW_DATA_DIR / "worldclim" / "wc2.1_10m_elev.zip",
    "ntca_archive": RAW_DATA_DIR / "protected_areas" / "PA_TR_Corridor_Final.zip",
    "ntca_kml": RAW_DATA_DIR / "protected_areas" / "extracted" / "PA_TR_Corridor_Final.kml",
}

LOCAL_TABLES = {
    "india_biodiversity_combined": DATA_DIR.parent / "extinct-species-since-1500" / "data" / "India_Biodiversity_Combined.xlsx",
    "india_biodiversity_master": DATA_DIR.parent / "extinct-species-since-1500" / "data" / "INDIA_BIODIVERSITY_MASTER_15K.xls",
    "iucn_ready_indian_biodiversity": DATA_DIR.parent / "extinct-species-since-1500" / "data" / "IUCN_READY_INDIAN_BIODIVERSITY.xls",
}

PIPELINE_STEPS = [
    {"script": "00_species_list.py", "output": "species_list.csv", "needs_network": False},
    {"script": "01_gbif_occurrences.py", "output": "occurrences_raw.csv", "needs_network": True},
    {"script": "02_iucn_data.py", "output": "iucn_traits.csv", "needs_network": True},
    {"script": "03_merge_and_eri.py", "output": "species_eri.json", "needs_network": False},
    {"script": "04_trends_and_state_db.py", "output": "state_species.json", "needs_network": False},
    {"script": "05_hotspots.py", "output": "hotspots.geojson", "needs_network": False},
    {"script": "06_trajectory_ml.py", "output": "watchlist.json", "needs_network": False},
]


def _file_info(path: Path) -> dict[str, object]:
    exists = path.exists()
    info: dict[str, object] = {
        "path": str(path),
        "exists": exists,
    }
    if exists and path.is_file():
        stat = path.stat()
        info.update(
            {
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return info


def _count_kml_placemarks(path: Path) -> int | None:
    if not path.exists():
        return None
    count = 0
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), ""):
            if not chunk:
                break
            count += chunk.count("<Placemark>")
    return count


def _candidate_output(name: str) -> Path | None:
    processed = PROCESSED_DATA_DIR / name
    if processed.exists():
        return processed
    legacy = DATA_DIR / name
    if legacy.exists():
        return legacy
    return None


# Only the derived dashboard files are served. Other processed files hold licensed source data
# (IUCN, WDPA, OSM) whose terms forbid offering it for download.
PUBLIC_OUTPUTS = ("state_species.json", "occurrence_points.json", "hotspots.geojson")


def list_output_files() -> list[dict[str, object]]:
    return [
        {"name": name, "exists": path is not None}
        for name in PUBLIC_OUTPUTS
        for path in [_candidate_output(name)]
    ]


def load_output_json(name: str) -> object | None:
    if name not in PUBLIC_OUTPUTS:
        return None
    path = _candidate_output(name)
    if path is None or path.suffix.lower() not in {".json", ".geojson"}:
        return None
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return json.load(handle)


def build_dataset_catalog() -> dict[str, object]:
    ntca_info = _file_info(RAW_FILES["ntca_kml"])
    ntca_info["placemarks"] = _count_kml_placemarks(RAW_FILES["ntca_kml"])
    status_text = ""
    if DATASET_STATUS_FILE.exists():
        status_text = DATASET_STATUS_FILE.read_text(encoding="utf-8", errors="ignore")

    return {
        "raw_downloads": {name: _file_info(path) for name, path in RAW_FILES.items()},
        "local_tables": {name: _file_info(path) for name, path in LOCAL_TABLES.items()},
        "ntca_summary": ntca_info,
        "dataset_status_file": _file_info(DATASET_STATUS_FILE),
        "dataset_status_preview": status_text[:2000],
    }


def build_phase_summary() -> dict[str, object]:
    steps: list[dict[str, object]] = []
    for step in PIPELINE_STEPS:
        script_path = SCRIPTS_DIR / step["script"]
        output_path = _candidate_output(step["output"])
        steps.append(
            {
                **step,
                "script_present": script_path.exists(),
                "output_present": output_path is not None,
                "output_path": str(output_path) if output_path else None,
            }
        )

    return {
        "phase": 1,
        "focus": "foundation, datasets, API scaffolding, and pipeline organization",
        "steps": steps,
        "processed_output_count": len(list_output_files()),
    }
