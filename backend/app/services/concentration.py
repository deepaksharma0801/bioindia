from __future__ import annotations

import os
from typing import Any


GRID_SIZE_DEGREES = 0.75


def biodiversity_concentration(limit: int) -> dict[str, Any] | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    import psycopg
    from psycopg.rows import dict_row

    query = """
        WITH cells AS (
            SELECT floor(longitude / %(grid_size)s) * %(grid_size)s AS longitude_min,
                   floor(latitude / %(grid_size)s) * %(grid_size)s AS latitude_min,
                   COUNT(*)::integer AS occurrence_record_count,
                   COUNT(DISTINCT species_id)::integer AS observed_species_count,
                   COUNT(DISTINCT year)::integer AS years_with_records,
                   MIN(year)::integer AS first_record_year,
                   MAX(year)::integer AS last_record_year
            FROM occurrences
            GROUP BY 1, 2
        )
        SELECT ROW_NUMBER() OVER (
                   ORDER BY occurrence_record_count DESC,
                            observed_species_count DESC,
                            years_with_records DESC,
                            longitude_min,
                            latitude_min
               )::integer AS record_concentration_rank,
               COUNT(*) OVER ()::integer AS total_grid_cell_count,
               occurrence_record_count,
               observed_species_count,
               years_with_records,
               first_record_year,
               last_record_year,
               ST_AsGeoJSON(ST_MakeEnvelope(
                   longitude_min,
                   latitude_min,
                   longitude_min + %(grid_size)s,
                   latitude_min + %(grid_size)s,
                   4326
               ))::jsonb AS geometry
        FROM cells
        ORDER BY record_concentration_rank
        LIMIT %(limit)s
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"grid_size": GRID_SIZE_DEGREES, "limit": limit})
                rows = cursor.fetchall()
    except psycopg.Error:
        return None

    if not rows:
        return None
    total_grid_cell_count = rows[0]["total_grid_cell_count"]
    features = []
    for row in rows:
        geometry = row.pop("geometry")
        row.pop("total_grid_cell_count")
        features.append({"type": "Feature", "geometry": geometry, "properties": row})
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "grid_size_degrees": GRID_SIZE_DEGREES,
            "returned_grid_cell_count": len(features),
            "total_grid_cell_count": total_grid_cell_count,
            "truncated": len(features) < total_grid_cell_count,
            "ranking": "descending loaded occurrence-record count; ties use observed species and years with records",
            "scope": "five tracked species in the loaded GBIF occurrence records",
            "conservation_priority": {
                "available": True,
                "endpoint": "/api/v1/analytics/conservation-priority",
                "note": "Protection-gap screening with separate components; habitat pressure and climate exposure are not yet included.",
            },
            "caveat": "Record concentration and observed species counts describe the loaded dataset. They are not population abundance, sampling-corrected biodiversity richness, irreplaceability, or a conservation-priority assessment.",
        },
    }
