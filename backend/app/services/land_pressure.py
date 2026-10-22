from __future__ import annotations

import os
from typing import Any


def species_land_pressure(species_id: str) -> dict[str, Any] | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    import psycopg
    from psycopg.errors import UndefinedTable
    from psycopg.rows import dict_row

    query = """
        SELECT COUNT(*) AS matched_occurrence_count,
               AVG(tree_cover_percent) AS mean_tree_cover_percent,
               COUNT(tree_cover_loss_year) AS records_with_tree_cover_loss_year,
               ARRAY_AGG(DISTINCT land_cover_class ORDER BY land_cover_class) AS land_cover_classes,
               MIN(land_cover_year) AS earliest_land_cover_year,
               MAX(land_cover_year) AS latest_land_cover_year,
               ARRAY_AGG(DISTINCT lp.source ORDER BY lp.source) AS sources
        FROM occurrence_land_pressure AS lp
        JOIN occurrences AS o ON o.occurrence_id = lp.occurrence_id
        WHERE o.species_id = %s
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (species_id,))
                profile = cursor.fetchone()
    except UndefinedTable:
        return None

    if not profile or not profile["matched_occurrence_count"]:
        return None
    return {
        "profile": profile,
        "methodology_note": "This reports imported land-cover and forest-change attributes at occurrence locations. It does not calculate a habitat-pressure score or demonstrate causal effects on the species.",
    }
