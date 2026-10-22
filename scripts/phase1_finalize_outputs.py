from __future__ import annotations

import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"

EXPECTED_OUTPUTS = [
    "species_list.csv",
    "occurrences_raw.csv",
    "occurrences_by_state.csv",
    "occurrences_by_year.csv",
    "iucn_traits.csv",
    "iucn_assessments.csv",
    "species_master.csv",
    "species_eri.json",
    "species_trends.json",
    "state_species.json",
    "hotspots.geojson",
    "gap_table.csv",
    "watchlist.json",
]


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    missing = []

    for filename in EXPECTED_OUTPUTS:
        source = DATA_DIR / filename
        target = PROCESSED_DIR / filename
        if source.exists() and source.is_file():
            shutil.copy2(source, target)
            copied.append(target)
        else:
            missing.append(filename)

    print("Phase 1 output organizer")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Copied {len(copied)} files into {PROCESSED_DIR}")
    for path in copied:
        print(f"  - {path.name}")

    if missing:
        print("\nNot present yet:")
        for filename in missing:
            print(f"  - {filename}")


if __name__ == "__main__":
    main()
