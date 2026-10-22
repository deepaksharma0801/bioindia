from __future__ import annotations

import os
from pathlib import Path


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = Path(os.getenv("BIOINDIA_PROJECT_ROOT", _default_project_root())).resolve()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
HTML_FILE = PROJECT_ROOT / "BioIndia_v3_Complete.html"
DATASET_STATUS_FILE = RAW_DATA_DIR / "DATASET_STATUS.md"

# Browser origins allowed to call the API (comma-separated); defaults to the local dashboard server.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("BIOINDIA_CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",")
    if origin.strip()
]
