"""Phase 13: data-derived concentration zones and conservation-priority (protection-gap) screening.

Reads the precomputed analytics_grid_cells table. Every component is returned separately and no
weighted composite is calculated; thresholds are request parameters with documented defaults.
"""

from __future__ import annotations

from typing import Any

from .db import fetch_all
from .protection import species_protection


RANKINGS = {
    "observed_species": "observed_species DESC, record_count DESC",
    "threatened_species": "threatened_species DESC, record_count DESC",
    "records": "record_count DESC, observed_species DESC",
    "records_within_10_km": "records_within_10_km DESC, record_count DESC",
}
UNAVAILABLE_COMPONENTS = {
    "endemism": "not available for the five tracked species",
    "habitat_pressure": "land-use and forest-change data not yet integrated (Phase 10)",
    "climate_exposure": "climate-change exposure not yet integrated; only baseline climate exists (Phase 9)",
}
CAVEATS = [
    "These are data-derived concentration zones for five tracked species, not officially recognised biodiversity hotspots.",
    "Species counts are observed in loaded records only; they reflect where people record more and are not sampling-corrected richness.",
    "Threatened status uses the project's source-reported categories until an IUCN import verifies them (see threatened_status_verified).",
    "Protected-area coverage is the share of each cell's area inside the layer; it is not a measure of management effectiveness.",
]

CELL_COLUMNS = """
    cell_id, ST_AsGeoJSON(geom)::jsonb AS geometry, dominant_state, record_count, records_within_10_km,
    observed_species, observed_species_within_10_km, species_ids, threatened_species, threatened_species_ids,
    threatened_status_verified, years_with_records, first_year, last_year, recent_records, dataset_count,
    wildlife_pa_pct, tiger_reserve_pct, forest_pct, other_designation_pct, grid_size_degrees, built_at
"""


def _feature_collection(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    grid_size = rows[0]["grid_size_degrees"]
    built_at = rows[0]["built_at"]
    features = []
    for rank, row in enumerate(rows, start=1):
        geometry = row.pop("geometry")
        row.pop("built_at")
        row.pop("grid_size_degrees")
        features.append({"type": "Feature", "geometry": geometry, "properties": {"rank": rank, **row}})
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            **metadata,
            "returned_cells": len(features),
            "grid_size_degrees": grid_size,
            "built_at": built_at.isoformat(),
            "unavailable_components": UNAVAILABLE_COMPONENTS,
            "caveats": CAVEATS,
        },
    }


def concentration_zones(rank_by: str, limit: int) -> dict[str, Any] | None:
    if rank_by not in RANKINGS:
        raise ValueError(f"rank_by must be one of: {', '.join(RANKINGS)}.")
    rows = fetch_all(f"SELECT {CELL_COLUMNS} FROM analytics_grid_cells ORDER BY {RANKINGS[rank_by]}, cell_id LIMIT %(limit)s", {"limit": limit})
    if not rows:
        return None
    total = fetch_all("SELECT COUNT(*)::integer AS n FROM analytics_grid_cells")[0]["n"]
    return _feature_collection(rows, {"ranking": rank_by, "total_cells": total})


def conservation_priority(min_threatened_species: int, max_wildlife_pa_pct: float, min_records_within_10_km: int, limit: int) -> dict[str, Any] | None:
    """Protection-gap screen: cells with threatened species but little wildlife protected-area cover."""
    criteria = {
        "min_threatened_species": min_threatened_species,
        "max_wildlife_pa_pct": max_wildlife_pa_pct,
        "min_records_within_10_km": min_records_within_10_km,
    }
    rows = fetch_all(
        f"""SELECT {CELL_COLUMNS} FROM analytics_grid_cells
            WHERE threatened_species >= %(min_threatened_species)s
              AND wildlife_pa_pct <= %(max_wildlife_pa_pct)s
              AND records_within_10_km >= %(min_records_within_10_km)s
            ORDER BY threatened_species DESC, wildlife_pa_pct ASC, record_count DESC, cell_id
            LIMIT %(limit)s""",
        {**criteria, "limit": limit},
    )
    total = fetch_all("SELECT COUNT(*)::integer AS n FROM analytics_grid_cells")[0]["n"]
    if not total:
        return None
    if not rows:
        return {"type": "FeatureCollection", "features": [], "metadata": {"criteria": criteria, "total_cells": total, "returned_cells": 0, "caveats": CAVEATS}}
    return _feature_collection(rows, {
        "criteria": criteria,
        "criteria_note": "Thresholds are request parameters, not established standards; compare several settings before drawing conclusions.",
        "ordering": "threatened species (desc), wildlife protected-area cover (asc), records (desc); no composite score",
        "total_cells": total,
    })


def threatened_species() -> list[dict[str, Any]]:
    rows = fetch_all(
        """SELECT s.species_id, s.common_name, s.scientific_name,
                  COALESCE(verified.iucn_category, s.current_iucn_status) AS category,
                  verified.iucn_category IS NOT NULL AS category_verified,
                  CASE WHEN verified.iucn_category IS NOT NULL THEN 'IUCN Red List import' ELSE s.current_iucn_status_source END AS category_source,
                  COUNT(o.occurrence_id)::integer AS records,
                  COUNT(DISTINCT o.state)::integer AS states_with_records,
                  (SELECT COUNT(*)::integer FROM analytics_grid_cells AS c WHERE s.species_id = ANY(c.species_ids)) AS grid_cells_occupied
           FROM species AS s
           LEFT JOIN occurrences AS o ON o.species_id = s.species_id
           LEFT JOIN LATERAL (
               SELECT ca.iucn_category FROM conservation_assessments AS ca
               WHERE ca.species_id = s.species_id ORDER BY ca.assessment_year DESC LIMIT 1
           ) AS verified ON TRUE
           WHERE COALESCE(verified.iucn_category, s.current_iucn_status) IN ('CR', 'EN', 'VU')
           GROUP BY s.species_id, verified.iucn_category
           ORDER BY CASE COALESCE(verified.iucn_category, s.current_iucn_status) WHEN 'CR' THEN 1 WHEN 'EN' THEN 2 ELSE 3 END, s.common_name"""
    )
    for row in rows:
        protection = species_protection(row["species_id"])
        row["wildlife_pa_record_percent_within_10_km"] = (protection or {}).get("wildlife_protected_areas", {}).get("record_intersection_percent")
        row["records_used_for_protection"] = (protection or {}).get("records_used", {}).get("count")
    return rows
