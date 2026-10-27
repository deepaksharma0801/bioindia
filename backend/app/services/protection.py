from __future__ import annotations

import os
from typing import Any


# Wildlife protected areas are the main protection layer; the other classes are reported separately.
PROTECTION_CLASSES = ("wildlife_pa", "tiger_reserve", "forest", "other_designation")
# Only records located to within 10 km are overlaid; coarser points (often deliberately obscured)
# can sit tens of km from the true location and would distort the percentages.
ELIGIBLE_UNCERTAINTY_CLASSES = ("precise", "moderate")
MAX_UNCERTAINTY_M = 10_000
SMALL_SAMPLE = 30

# Point-in-polygon tests run against protected_areas_sub (the same outlines cut into small pieces by
# scripts/phase11_subdivide_protected_areas.py), which is far faster than the original polygons.
PROTECTION_QUERY = """
    SELECT COUNT(*) AS occurrence_record_count,
           COUNT(*) FILTER (WHERE o.coordinate_uncertainty_class = ANY(%(eligible)s)) AS eligible_record_count,
           COUNT(*) FILTER (WHERE o.coordinate_uncertainty_class = 'coarse') AS coarse_records_left_out,
           COUNT(*) FILTER (WHERE o.coordinate_uncertainty_class = 'unknown') AS unknown_uncertainty_records_left_out,
           {class_counts},
           (SELECT ARRAY_AGG(DISTINCT source_version ORDER BY source_version) FROM protected_areas) AS source_versions
    FROM occurrences AS o
    WHERE o.species_id = %(species_id)s
""".format(
    class_counts=",\n           ".join(
        f"""COUNT(*) FILTER (WHERE o.coordinate_uncertainty_class = ANY(%(eligible)s) AND EXISTS (
               SELECT 1 FROM {{table}} AS pa
               WHERE pa.pa_class = '{pa_class}' AND ST_Intersects(o.geom, pa.geom)
           )) AS {pa_class}"""
        for pa_class in PROTECTION_CLASSES
    )
)


def summarize_protection(result: dict[str, Any]) -> dict[str, Any] | None:
    total = int(result.get("occurrence_record_count") or 0)
    if not total:
        return None
    eligible = int(result.get("eligible_record_count") or 0)
    layers = {
        pa_class: {
            "records_intersecting": int(result[pa_class]),
            "record_intersection_percent": round(100 * int(result[pa_class]) / eligible, 2) if eligible else None,
        }
        for pa_class in PROTECTION_CLASSES
    }
    return {
        "occurrence_record_count": total,
        "records_used": {
            "count": eligible,
            "rule": f"records with stated coordinate uncertainty of at most {MAX_UNCERTAINTY_M // 1000} km",
            "small_sample_warning": eligible < SMALL_SAMPLE,
        },
        "records_left_out": {
            "coarse_over_10_km": int(result.get("coarse_records_left_out") or 0),
            "uncertainty_not_stated": int(result.get("unknown_uncertainty_records_left_out") or 0),
            "reason": "Coarse coordinates are usually obscured by the publisher to protect threatened species and can lie tens of km from the true location; records without a stated uncertainty cannot be checked.",
        },
        "wildlife_protected_areas": layers["wildlife_pa"],
        "reported_separately": {
            "tiger_reserves": layers["tiger_reserve"],
            "legal_forest_categories": layers["forest"],
            "other_designations": layers["other_designation"],
        },
        "sources": {
            "wildlife_protected_areas": "OpenStreetMap contributors (ODbL 1.0)",
            "tiger_reserves": "OpenStreetMap contributors (ODbL 1.0)",
            "legal_forest_categories": "UNEP-WCMC and IUCN, Protected Planet WDPA/WD-OECM",
            "other_designations": "UNEP-WCMC and IUCN, Protected Planet WDPA/WD-OECM",
        },
        "source_versions": result.get("source_versions"),
        "definitions": {
            "wildlife_protected_areas": "National Parks, Wildlife Sanctuaries, Conservation Reserves and Community Reserves mapped in OpenStreetMap.",
            "tiger_reserves": "Tiger reserves mapped in OpenStreetMap. They include buffer zones, so they are not part of the wildlife protected-area figure.",
            "legal_forest_categories": "Reserve, Reserved, Protected and Unclassed Forests from WDPA. These are forest-law categories, not wildlife protected areas.",
            "other_designations": "Ramsar sites, Biodiversity Heritage Sites, Biosphere Reserves and other WDPA designations.",
        },
        "methodology_note": "Each percentage is the share of the records used (within 10 km) intersecting that layer; it is null when no records qualify. It is not an estimate of habitat protection, range protection, or conservation effectiveness. Proposed sites, eco-sensitive zones, buffers and corridors are excluded.",
        "limitation": "OpenStreetMap boundaries are community-mapped and not an official Government of India list; some sites may be missing or approximate.",
    }


def _sub_table_exists(cursor) -> bool:
    cursor.execute("SELECT to_regclass('protected_areas_sub') IS NOT NULL AS present")
    return cursor.fetchone()["present"]


# Results depend only on loaded data, so successful ones are cached per process (restart the API after reloading data).
_CACHE: dict[str, dict[str, Any]] = {}


def species_protection(species_id: str) -> dict[str, Any] | None:
    if species_id in _CACHE:
        return _CACHE[species_id]
    result = _species_protection(species_id)
    if result is not None:
        _CACHE[species_id] = result
    return result


def _species_protection(species_id: str) -> dict[str, Any] | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    import psycopg
    from psycopg.errors import UndefinedTable
    from psycopg.rows import dict_row

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('protected_areas_sub') IS NOT NULL AND EXISTS (SELECT 1 FROM protected_areas_sub) AS ready"
                               if _sub_table_exists(cursor) else "SELECT FALSE AS ready")
                table = "protected_areas_sub" if cursor.fetchone()["ready"] else "protected_areas"
                cursor.execute(PROTECTION_QUERY.replace("{table}", table), {"species_id": species_id, "eligible": list(ELIGIBLE_UNCERTAINTY_CLASSES)})
                result = cursor.fetchone()
    except UndefinedTable:
        return None
    return summarize_protection(result) if result else None
