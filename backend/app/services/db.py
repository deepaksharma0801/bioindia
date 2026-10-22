from __future__ import annotations

import os
from typing import Any


class DatabaseUnavailable(RuntimeError):
    """Raised when DATABASE_URL is unset or the database cannot be reached; mapped to HTTP 503."""


def fetch_all(query: str, parameters: dict[str, Any] | tuple | None = None) -> list[dict[str, Any]]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseUnavailable("DATABASE_URL is not configured.")

    import psycopg
    from psycopg.rows import dict_row

    try:
        connection = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5)
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable("The occurrence database cannot be reached.") from error
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall()
