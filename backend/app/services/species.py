from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

from .conservation import official_assessment
from .db import fetch_all
from .environment import species_environment
from .land_pressure import species_land_pressure
from .protection import species_protection


TREND_START_YEAR = 2000
MAX_MAP_POINTS_PER_SPECIES = 500
STATE_ATTRIBUTION = "point-in-polygon against geoBoundaries IND ADM1, nearest state within a 10 km coastal tolerance"

# Presentation only: the dashboard's artwork is keyed by these emoji, and the map colours match the original design.
SPECIES_DISPLAY = {
    "tiger": {"emoji": "\U0001F42F", "color": "#ff6030"},
    "elephant": {"emoji": "\U0001F418", "color": "#6090d0"},
    "rhino": {"emoji": "\U0001F98F", "color": "#4abaa8"},
    "bear": {"emoji": "\U0001F43B", "color": "#c07830"},
    "croc": {"emoji": "\U0001F40A", "color": "#30a080"},
}

FLAGSHIP_IDS = tuple(SPECIES_DISPLAY)


def display_color(species_id: str) -> str:
    """Flagship colours from the original design; a stable generated colour for every other species."""
    if species_id in SPECIES_DISPLAY:
        return SPECIES_DISPLAY[species_id]["color"]
    hue = int(hashlib.sha1(species_id.encode("utf-8")).hexdigest()[:4], 16) % 360
    return f"hsl({hue}, 55%, 55%)"


SPECIES_QUERY = """
    SELECT s.species_id, s.common_name, s.scientific_name, s.class_name,
           s.kingdom, s.phylum, s.order_name, s.family, s.genus, s.species_epithet, s.gbif_taxon_key,
           s.current_iucn_status, s.current_iucn_status_source, s.source, s.source_dataset_identifier,
           (SELECT ca.iucn_category FROM conservation_assessments AS ca
            WHERE ca.species_id = s.species_id ORDER BY ca.assessment_year DESC LIMIT 1) AS official_iucn_status,
           (SELECT ca.taxon_level FROM conservation_assessments AS ca
            WHERE ca.species_id = s.species_id ORDER BY ca.assessment_year DESC LIMIT 1) AS official_assessment_taxon_level,
           COUNT(o.occurrence_id)::integer AS observation_record_count,
           COUNT(DISTINCT o.state)::integer AS states_with_records
    FROM species AS s
    LEFT JOIN occurrences AS o ON o.species_id = s.species_id
    WHERE (%(species_id)s::text IS NULL OR s.species_id = %(species_id)s)
    GROUP BY s.species_id
    ORDER BY s.common_name
"""


def _last_complete_year() -> int:
    return date.today().year - 1


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "species_id": row["species_id"],
        "common_name": row["common_name"],
        "scientific_name": row["scientific_name"],
        "taxonomic_group": row["class_name"],
        "official_iucn_status": row["official_iucn_status"],
        # 'subspecies' or 'subpopulation' means the category is for the Indian taxon, not the species globally.
        "official_assessment_taxon_level": row["official_assessment_taxon_level"],
        "source_reported_iucn_status": row["current_iucn_status"],
        "states_with_records": row["states_with_records"],
        "observation_record_count": row["observation_record_count"],
    }


def _species_rows(species_id: str | None = None) -> list[dict[str, Any]]:
    return fetch_all(SPECIES_QUERY, {"species_id": species_id})


def list_species(query: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    normalized_query = (query or "").strip().casefold()
    normalized_status = (status or "").strip().upper()
    results = []
    for row in _species_rows():
        summary = _summary(row)
        names = [str(summary[key] or "").casefold() for key in ("species_id", "scientific_name", "common_name")]
        if normalized_query:
            # 0 = exact name, 1 = a name or word starts with the query, 2 = contained anywhere.
            if normalized_query in names:
                rank = 0
            elif any(word.startswith(normalized_query) for name in names for word in name.replace("_", " ").split()):
                rank = 1
            elif any(normalized_query in name for name in names):
                rank = 2
            else:
                continue
        else:
            rank = 0
        category = summary["official_iucn_status"] or summary["source_reported_iucn_status"] or ""
        if normalized_status and category.upper() != normalized_status:
            continue
        results.append((rank, summary))
    return [summary for _, summary in sorted(results, key=lambda item: item[0])]


def get_species(species_id: str) -> dict[str, Any] | None:
    rows = _species_rows(species_id)
    return _summary(rows[0]) if rows else None


def _annual_counts(species_id: str | None = None) -> dict[str, dict[int, int]]:
    rows = fetch_all(
        """SELECT species_id, year, COUNT(*)::integer AS records FROM occurrences
           WHERE year BETWEEN %(start)s AND %(end)s AND (%(species_id)s::text IS NULL OR species_id = %(species_id)s)
           GROUP BY species_id, year""",
        {"start": TREND_START_YEAR, "end": _last_complete_year(), "species_id": species_id},
    )
    counts: dict[str, dict[int, int]] = {}
    for row in rows:
        counts.setdefault(row["species_id"], {})[row["year"]] = row["records"]
    return counts


def _normalized_index(counts: dict[int, int]) -> list[int]:
    years = range(TREND_START_YEAR, _last_complete_year() + 1)
    raw = [counts.get(year, 0) for year in years]
    peak = max(raw) if raw else 0
    return [round(100 * value / peak) if peak else 0 for value in raw]


def species_trend(species_id: str) -> dict[str, Any] | None:
    if get_species(species_id) is None:
        return None
    counts = _annual_counts(species_id).get(species_id, {})
    return {
        "species_id": species_id,
        "years": list(range(TREND_START_YEAR, _last_complete_year() + 1)),
        "normalized_observation_index": _normalized_index(counts),
        "record_counts": [counts.get(year, 0) for year in range(TREND_START_YEAR, _last_complete_year() + 1)],
        "methodology_note": "This is a normalized occurrence-record index (peak year = 100), not a population-abundance estimate. The current, incomplete year is excluded.",
    }


def species_occurrences(species_id: str | None = None, all_species: bool = False) -> dict[str, Any] | None:
    """Map payload in the dashboard's format: grouped points per species (same place, year).

    Without a species_id the five flagship species are returned unless all_species is set, which
    keeps the dashboard map light now that the platform tracks many species.
    """
    species = _species_rows(species_id)
    if species_id and not species:
        return None
    if not species_id and not all_species:
        species = [row for row in species if row["species_id"] in FLAGSHIP_IDS]
    points = fetch_all(
        """SELECT species_id, ROUND(latitude::numeric, 3)::float AS lat, ROUND(longitude::numeric, 3)::float AS lng,
                  year, MODE() WITHIN GROUP (ORDER BY state) AS state, COUNT(*)::integer AS obs,
                  MODE() WITHIN GROUP (ORDER BY coordinate_uncertainty_class) AS uncertainty_class
           FROM occurrences WHERE species_id = ANY(%(species_ids)s)
           GROUP BY species_id, 2, 3, year
           ORDER BY species_id, obs DESC, year DESC""",
        {"species_ids": [row["species_id"] for row in species]},
    )
    by_species: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        grouped = by_species.setdefault(point.pop("species_id"), [])
        if len(grouped) < MAX_MAP_POINTS_PER_SPECIES:
            grouped.append({**point, "uncertaintyClass": point.pop("uncertainty_class")})
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceMode": "postgis_gbif_occurrences",
        "note": f"Points are grouped by rounded location and year; at most {MAX_MAP_POINTS_PER_SPECIES} groups per species. Points classed 'coarse' are deliberately obscured and may lie tens of km from the true location.",
        "species": [
            {
                "id": row["species_id"],
                "name": row["common_name"],
                "scientificName": row["scientific_name"],
                "status": row["official_iucn_status"] or row["current_iucn_status"],
                "statusVerified": bool(row["official_iucn_status"]),
                "col": display_color(row["species_id"]),
                "emoji": SPECIES_DISPLAY.get(row["species_id"], {}).get("emoji"),
                "totalRawRecords": row["observation_record_count"],
                "groupedPointCount": len(by_species.get(row["species_id"], [])),
                "points": by_species.get(row["species_id"], []),
            }
            for row in species
        ],
    }


def state_profiles() -> dict[str, list[dict[str, Any]]]:
    """Per-state species entries in the dashboard's STATE_DB format, from loaded occurrences."""
    species = {row["species_id"]: row for row in _species_rows()}
    trends = {species_id: _normalized_index(counts) for species_id, counts in _annual_counts().items()}
    rows = fetch_all(
        """SELECT state, species_id, COUNT(*)::integer AS obs, MIN(year) AS first_year, MAX(year) AS last_year
           FROM occurrences WHERE state IS NOT NULL GROUP BY state, species_id ORDER BY state, obs DESC"""
    )
    profiles: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        info = species[row["species_id"]]
        category = info["official_iucn_status"] or info["current_iucn_status"] or ""
        profiles.setdefault(row["state"], []).append({
            "species_id": row["species_id"],
            "e": SPECIES_DISPLAY.get(row["species_id"], {}).get("emoji", ""),
            "n": info["common_name"],
            "s": info["scientific_name"],
            "st": category.lower(),
            "status_verified": bool(info["official_iucn_status"]),
            "h": "Habitat data not yet integrated",
            "obs": row["obs"],
            "trend": trends.get(row["species_id"], _normalized_index({})),
            "desc": f"{row['obs']} GBIF occurrence records in {row['state']} ({row['first_year']}-{row['last_year']}). Records are observations, not population counts.",
            "eri": None,
            "taxonomic_group": info["class_name"],
        })
    return profiles


def species_intelligence(species_id: str) -> dict[str, Any] | None:
    rows = _species_rows(species_id)
    if not rows:
        return None
    row = rows[0]
    trend = species_trend(species_id)
    verified_assessment = official_assessment(species_id)
    states = [item["state"] for item in fetch_all(
        "SELECT state, COUNT(*) AS n FROM occurrences WHERE species_id = %(species_id)s AND state IS NOT NULL GROUP BY state ORDER BY n DESC",
        {"species_id": species_id},
    )]
    return {
        "species": _summary(row),
        "taxonomy": {
            key: row[key]
            for key in ("kingdom", "phylum", "class_name", "order_name", "family", "genus", "species_epithet", "gbif_taxon_key")
        },
        "conservation_assessment": {
            "category": (verified_assessment or {}).get("iucn_category") or row["current_iucn_status"],
            "source": (verified_assessment or {}).get("source") or row["current_iucn_status_source"],
            "official_assessment_verified": bool(verified_assessment),
            "note": "Official assessment data are shown only after a provenance-validated import." if verified_assessment else "This source-reported category has not been independently verified against an IUCN assessment in this project.",
        },
        "occurrence_history": {
            "record_count": row["observation_record_count"],
            "trend": trend,
            "source": row["source_dataset_identifier"],
            "note": "Occurrence records and their normalized index are not population-abundance estimates.",
        },
        "geographic_distribution": {
            "states_with_records": states,
            "attribution_method": STATE_ATTRIBUTION,
            "uncertainty_note": "Many records are deliberately obscured (> 10 km); state attribution near borders is approximate.",
        },
        "protected_area_coverage": species_protection(species_id),
        "habitat": {"available": False, "reported_summary": None, "source": None},
        "derived_watchlist_signal": {
            "available": False,
            "note": "No model-based risk signal yet; the extinction-vulnerability model is a later phase.",
        },
        "data_gaps": {
            "population_trend": "not available from occurrence records",
            "habitat": "not yet integrated",
            "environmental_exposure": "not yet integrated",
            "documented_ecological_network": "not yet integrated",
        },
    }


def _assessment_note(assessment: dict[str, Any] | None) -> str:
    if not assessment:
        return "Official assessment fields are unavailable until an authorized IUCN export is imported."
    if assessment.get("taxon_level") and assessment["taxon_level"] != "species":
        return (f"Official IUCN assessment of {assessment['assessed_taxon_name']} ({assessment['taxon_level']}); "
                "it describes that taxon, not the species' global status.")
    return "Imported official assessment data with recorded provenance."


def species_conservation_status(species_id: str) -> dict[str, Any] | None:
    rows = _species_rows(species_id)
    if not rows:
        return None
    row = rows[0]
    verified_assessment = official_assessment(species_id)
    return {
        "species": _summary(row),
        "official_assessment": {
            "available": bool(verified_assessment),
            "verified": bool(verified_assessment),
            "data": verified_assessment,
            "note": _assessment_note(verified_assessment),
        },
        "source_reported_category": {
            "category": row["current_iucn_status"],
            "source": row["current_iucn_status_source"],
            "note": "This category comes from the project's reference list and is not an independently verified official assessment.",
        },
    }


def species_environment_profile(species_id: str) -> dict[str, Any] | None:
    if get_species(species_id) is None:
        return None
    return species_environment(species_id)


def species_land_pressure_profile(species_id: str) -> dict[str, Any] | None:
    if get_species(species_id) is None:
        return None
    return species_land_pressure(species_id)


def species_protection_profile(species_id: str) -> dict[str, Any] | None:
    if get_species(species_id) is None:
        return None
    return species_protection(species_id)
