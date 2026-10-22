from __future__ import annotations

from typing import Any

from ..config import DATA_DIR


CLIMATE_PROFILES = DATA_DIR / "analytics" / "species_climate_profiles.json"


def species_environment(species_id: str) -> dict[str, Any] | None:
    if not CLIMATE_PROFILES.exists():
        return None

    import json

    payload = json.loads(CLIMATE_PROFILES.read_text(encoding="utf-8"))
    profiles = payload.get("profiles") if isinstance(payload, dict) else None
    if not isinstance(profiles, list):
        return None
    profile = next((item for item in profiles if item.get("species_id") == species_id), None)
    if not isinstance(profile, dict):
        return None
    return {"profile": profile, "metadata": payload.get("metadata", {})}
