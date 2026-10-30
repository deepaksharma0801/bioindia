"""Pack the loaded database and the files the app reads into one zip, for setting up another machine.

Writes data/handoff/bioindia_data_bundle.zip. Unzipped in a fresh clone it gives bioindia.dump plus the
data/ files; docs/SETUP.md explains the restore. Needs the bioindia-postgis container to be running.

The bundle contains IUCN and WDPA derived data, whose terms restrict redistribution: share it privately
with project collaborators only, never publicly and never in git.

Usage: python scripts/make_data_bundle.py
"""

from __future__ import annotations

import subprocess
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "handoff"
BUNDLE = OUT_DIR / "bioindia_data_bundle.zip"
CONTAINER = "bioindia-postgis"
FILES = [
    "data/processed/state_species.json",
    "data/processed/occurrence_points.json",
    "data/processed/hotspots.geojson",
    "data/processed/species_images.json",
    "data/analytics/species_climate_profiles.json",
    "data/raw/india_states_admin_current.geojson",
]


def run(*command: str) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    started = time.monotonic()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dump = OUT_DIR / "bioindia.dump"
    print("Dumping the database (a few minutes)", flush=True)
    run("docker", "exec", CONTAINER, "pg_dump", "-U", "bioindia", "-d", "bioindia", "-Fc", "-Z", "6", "-f", "/tmp/bioindia.dump")
    run("docker", "cp", f"{CONTAINER}:/tmp/bioindia.dump", str(dump))
    run("docker", "exec", CONTAINER, "rm", "/tmp/bioindia.dump")

    print("Writing the zip", flush=True)
    with zipfile.ZipFile(BUNDLE, "w", allowZip64=True) as bundle:
        bundle.write(dump, "bioindia.dump", compress_type=zipfile.ZIP_STORED)  # already compressed
        for name in FILES:
            bundle.write(ROOT / name, name, compress_type=zipfile.ZIP_DEFLATED)
    dump.unlink()
    print(f"{BUNDLE} ({BUNDLE.stat().st_size / 1e9:.2f} GB) in {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
