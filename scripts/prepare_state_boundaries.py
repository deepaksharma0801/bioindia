"""Normalize geoBoundaries India ADM1 state names into data/raw/india_states_admin_current.geojson."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "raw" / "boundaries" / "geoBoundaries-IND-ADM1.geojson"
OUTPUT = ROOT / "data" / "raw" / "india_states_admin_current.geojson"

# Names after diacritics are stripped -> names used by the dashboard and pipeline scripts.
ALIASES = {
    "Andaman and Nicobar Islands": "Andaman & Nicobar",
    "Jammu and Kashmir": "Jammu & Kashmir",
    "Dadra and Nagar Haveli and Daman and Diu": "Dadra & Nagar Haveli and Daman & Diu",
}


def plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    for feature in payload["features"]:
        properties = feature["properties"]
        name = plain(properties["shapeName"])
        properties["state"] = ALIASES.get(name, name)
        properties["source"] = "geoBoundaries gbOpen IND ADM1 (DataMeet India community, Election Commission of India)"
        properties["license"] = "CC BY 2.5 IN"
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    names = sorted(feature["properties"]["state"] for feature in payload["features"])
    print(f"Wrote {OUTPUT} with {len(names)} states/UTs:")
    for name in names:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
