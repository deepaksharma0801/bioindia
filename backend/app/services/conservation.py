from __future__ import annotations

import os
from typing import Any


def official_assessment(species_id: str) -> dict[str, Any] | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    import psycopg
    from psycopg.errors import UndefinedTable
    from psycopg.rows import dict_row

    query = """
        SELECT iucn_taxon_id, iucn_category, assessment_year, population_trend,
               threat_codes, threat_descriptions, habitat_codes, conservation_actions,
               assessment_version, source, source_url, dataset_version, retrieval_date
        FROM conservation_assessments
        WHERE species_id = %s
        ORDER BY assessment_year DESC, imported_at DESC
        LIMIT 1
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (species_id,))
                return cursor.fetchone()
    except UndefinedTable:
        return None
