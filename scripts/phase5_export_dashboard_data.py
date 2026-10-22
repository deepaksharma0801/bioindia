"""Regenerate the dashboard's static data files from PostGIS.

The backend serves the same payloads live; these files are the frontend's fallback when it is
opened without the API (bioindia-phase2.js / bioindia-phase3.js look in data/processed/).
Built with the backend's own services so the files and the API never disagree.

Output: data/processed/state_species.json
        data/processed/occurrence_points.json
        data/processed/hotspots.geojson
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

from app.services.gis import hotspot_geojson  # noqa: E402
from app.services.species import species_occurrences, state_profiles  # noqa: E402


PROCESSED = ROOT / "data" / "processed"


def write(name: str, payload: object) -> None:
    path = PROCESSED / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    states = state_profiles()
    write("state_species.json", states)
    occurrences = species_occurrences()
    write("occurrence_points.json", occurrences)
    hotspots = hotspot_geojson()
    write("hotspots.geojson", hotspots)
    print(f"  {len(states)} states, {sum(len(entries) for entries in states.values())} state-species entries")
    print(f"  {sum(s['groupedPointCount'] for s in occurrences['species'])} grouped map points for {len(occurrences['species'])} species")
    print(f"  {len(hotspots['features'])} record concentration cells")


if __name__ == "__main__":
    main()
