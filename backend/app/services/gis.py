from __future__ import annotations

from typing import Any

from ..config import RAW_DATA_DIR
from .concentration import GRID_SIZE_DEGREES
from .db import fetch_all


STATE_BOUNDARIES_FILE = RAW_DATA_DIR / "india_states_admin_current.geojson"
HOTSPOT_LIMIT = 9

HOTSPOT_QUERY = """
    WITH cells AS (
        SELECT floor(longitude / %(grid)s) * %(grid)s AS lon_min,
               floor(latitude / %(grid)s) * %(grid)s AS lat_min,
               COUNT(*)::integer AS record_count,
               COUNT(DISTINCT species_id)::integer AS species_richness,
               COUNT(*) FILTER (WHERE coordinate_uncertainty_class = 'coarse')::integer AS coarse_records,
               MODE() WITHIN GROUP (ORDER BY state) AS dominant_state
        FROM occurrences
        GROUP BY 1, 2
    ), top AS (
        SELECT *, ST_MakeEnvelope(lon_min, lat_min, lon_min + %(grid)s, lat_min + %(grid)s, 4326) AS cell
        FROM cells
        ORDER BY record_count DESC, species_richness DESC, lon_min, lat_min
        LIMIT %(limit)s
    )
    SELECT lon_min, lat_min, record_count, species_richness, coarse_records, dominant_state,
           (SELECT MAX(record_count) FROM cells) AS max_record_count,
           ROUND((100 * COALESCE(ST_Area(ST_Intersection(cell, (
               SELECT ST_Union(geom) FROM protected_areas
               WHERE pa_class = 'wildlife_pa' AND ST_Intersects(geom, cell)
           ))::geography), 0) / ST_Area(cell::geography))::numeric, 1)::float AS pa_coverage_pct
    FROM top
    ORDER BY record_count DESC, species_richness DESC, lon_min, lat_min
"""


def hotspot_geojson(limit: int = HOTSPOT_LIMIT) -> dict[str, Any] | None:
    """Top grid cells by loaded occurrence records, in the dashboard's hotspot format."""
    rows = fetch_all(HOTSPOT_QUERY, {"grid": GRID_SIZE_DEGREES, "limit": limit})
    if not rows:
        return None
    tracked = fetch_all("SELECT count(*) AS n FROM species AS s WHERE EXISTS (SELECT 1 FROM occurrences AS o WHERE o.species_id = s.species_id)")[0]["n"]
    features = []
    for rank, row in enumerate(rows, start=1):
        lon, lat, size = row["lon_min"], row["lat_min"], GRID_SIZE_DEGREES
        score = round(100 * row["record_count"] / row["max_record_count"], 1)
        state = row["dominant_state"] or "Cross-state"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]]},
            "properties": {
                "rank": rank,
                "region_name": f"{state} record concentration cell",
                "dominant_state": state,
                "species_richness": row["species_richness"],
                "record_count": row["record_count"],
                "coarse_record_share_pct": round(100 * row["coarse_records"] / row["record_count"], 1),
                "hotspot_score": score,
                "hotspot_score_norm": score,
                "pa_coverage_pct": row["pa_coverage_pct"],
                "gap_status": "record concentration zone",
                "centroid_lat": round(lat + size / 2, 3),
                "centroid_lon": round(lon + size / 2, 3),
                "summary": f"{row['species_richness']} of the {tracked} tracked species and {row['record_count']} occurrence records; wildlife protected areas cover {row['pa_coverage_pct']}% of the cell.",
            },
        })
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "source": "GBIF occurrence records loaded into PostGIS (https://doi.org/10.15468/dl.dvgq2s)",
            "method": f"{GRID_SIZE_DEGREES}-degree grid; cells ranked by occurrence-record count, then observed species; score = records / busiest cell x 100",
            "protected_area_coverage": "share of the cell's area inside OpenStreetMap wildlife protected areas",
            "scope": f"{tracked} tracked species with loaded records",
            "caveat": "These are data-derived record concentration zones, not officially recognised biodiversity hotspots. Scores summarize occurrence records, not population abundance or biodiversity completeness, and reflect where people record more.",
        },
    }


def state_boundaries_info() -> dict[str, Any] | None:
    if not STATE_BOUNDARIES_FILE.exists():
        return None
    return {
        "source_file": STATE_BOUNDARIES_FILE.name,
        "download_url": "/api/v1/gis/state-boundaries",
        "coordinate_reference_system": "WGS 84 longitude/latitude coordinates",
        "note": "Administrative boundaries are a reference layer; state attribution for occurrence records is approximate near borders.",
    }


def occurrence_geojson(
    species_id: str | None,
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    limit: int,
    state: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    iucn_category: str | None = None,
    within_10_km_only: bool = False,
) -> dict[str, Any]:
    bbox_values = (west, south, east, north)
    if any(value is not None for value in bbox_values) and any(value is None for value in bbox_values):
        raise ValueError("west, south, east, and north must be supplied together.")
    if west is not None and (west >= east or south >= north):
        raise ValueError("Bounding box must have west < east and south < north.")
    if year_from is not None and year_to is not None and year_from > year_to:
        raise ValueError("year_from must not be later than year_to.")

    conditions: list[str] = []
    parameters: list[object] = []
    if species_id:
        conditions.append("o.species_id = %s")
        parameters.append(species_id)
    if west is not None:
        conditions.append("ST_Intersects(o.geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))")
        parameters.extend((west, south, east, north))
    if state:
        conditions.append("o.state = %s")
        parameters.append(state)
    if year_from is not None:
        conditions.append("o.year >= %s")
        parameters.append(year_from)
    if year_to is not None:
        conditions.append("o.year <= %s")
        parameters.append(year_to)
    if iucn_category:
        # Verified category when imported, otherwise the source-reported one.
        conditions.append(
            "UPPER(COALESCE((SELECT ca.iucn_category FROM conservation_assessments AS ca WHERE ca.species_id = o.species_id "
            "ORDER BY ca.assessment_year DESC LIMIT 1), s.current_iucn_status)) = %s"
        )
        parameters.append(iucn_category.upper())
    if within_10_km_only:
        conditions.append("o.coordinate_uncertainty_class IN ('precise', 'moderate')")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT o.species_id, s.scientific_name, s.common_name, o.event_date, o.date_precision, o.year,
               o.state, o.basis_of_record, o.coordinate_uncertainty, o.coordinate_uncertainty_class,
               ST_X(o.geom) AS longitude, ST_Y(o.geom) AS latitude
        FROM occurrences AS o
        JOIN species AS s ON s.species_id = o.species_id
        {where_clause}
        ORDER BY o.event_date DESC, o.occurrence_id
        LIMIT %s
    """
    parameters.append(limit + 1)
    rows = fetch_all(query, tuple(parameters))

    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
                "properties": {
                    "species_id": row["species_id"],
                    "scientific_name": row["scientific_name"],
                    "common_name": row["common_name"],
                    "event_date": row["event_date"].isoformat() if row["event_date"] else None,
                    "date_precision": row["date_precision"],
                    "year": row["year"],
                    "state": row["state"],
                    "basis_of_record": row["basis_of_record"],
                    "coordinate_uncertainty_m": row["coordinate_uncertainty"],
                    "coordinate_uncertainty_class": row["coordinate_uncertainty_class"],
                },
            }
            for row in rows
        ],
        "metadata": {
            "record_count": len(rows),
            "limit": limit,
            "truncated": truncated,
            "filters": {
                "species_id": species_id, "state": state, "year_from": year_from, "year_to": year_to,
                "iucn_category": iucn_category, "within_10_km_only": within_10_km_only,
                "bbox": list(bbox_values) if west is not None else None,
            },
            "source": "quality-controlled local occurrence records loaded into PostGIS",
            "observation_note": "Mapped occurrence records are observations, not population-abundance estimates.",
            "uncertainty_note": "Records classed 'coarse' (> 10 km) are usually deliberately obscured by the publisher; the mapped point is not the true location.",
        },
    }
