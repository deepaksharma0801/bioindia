from __future__ import annotations

import os
from typing import Any


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def species_observation_time_series(species_id: str) -> dict[str, Any] | None:
    database_url = _database_url()
    if not database_url:
        return None

    import psycopg
    from psycopg.rows import dict_row

    query = """
        WITH annual_dataset AS (
            SELECT year,
                   COUNT(*) AS all_species_observation_records,
                   COUNT(DISTINCT species_id) AS distinct_species_recorded
            FROM occurrences
            GROUP BY year
        ), annual_species AS (
            SELECT year, COUNT(*) AS species_observation_records
            FROM occurrences
            WHERE species_id = %s
            GROUP BY year
        )
        SELECT s.year,
               s.species_observation_records,
               d.all_species_observation_records,
               d.distinct_species_recorded,
               ROUND(
                   100.0 * s.species_observation_records / d.all_species_observation_records,
                   2
               ) AS within_dataset_record_share_percent
        FROM annual_species AS s
        JOIN annual_dataset AS d USING (year)
        ORDER BY s.year
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (species_id,))
                records = cursor.fetchall()
    except psycopg.Error:
        return None

    if not records:
        return None
    return {
        "species_id": species_id,
        "series": records,
        "coverage": {
            "first_year": records[0]["year"],
            "last_year": records[-1]["year"],
            "years_with_species_records": len(records),
        },
        "measure_type": "annual occurrence-record counts",
        "methodology_note": "Each year reports the species' loaded occurrence records and its share of all loaded records that year. The share describes this dataset's composition, not sampling effort or population change.",
        "limitation": "The loaded records have no independent survey-effort metadata. Neither the annual counts nor their within-dataset share is a population, abundance, occupancy, or conservation-status trend.",
    }


def biodiversity_observation_time_series() -> dict[str, Any] | None:
    database_url = _database_url()
    if not database_url:
        return None

    import psycopg
    from psycopg.rows import dict_row

    query = """
        SELECT year,
               COUNT(*) AS observation_records,
               COUNT(DISTINCT species_id) AS distinct_species_recorded,
               COUNT(DISTINCT dataset_key) AS distinct_dataset_keys,
               COUNT(DISTINCT basis_of_record) AS distinct_basis_of_record_values
        FROM occurrences
        GROUP BY year
        ORDER BY year
    """
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                records = cursor.fetchall()
    except psycopg.Error:
        return None

    if not records:
        return None
    return {
        "series": records,
        "coverage": {
            "first_year": records[0]["year"],
            "last_year": records[-1]["year"],
            "years_with_records": len(records),
        },
        "measure_type": "annual occurrence-record and observed-richness counts",
        "methodology_note": "Distinct species is the number represented in the loaded records for that year. It is observed dataset richness, not an estimate of regional biodiversity richness.",
        "limitation": "Annual record counts can change with reporting, digitization, geographic coverage, and sampling. No independent survey-effort measure is available, so this endpoint does not calculate a biodiversity-population or abundance trend.",
    }
