"""Rebuild protected_areas_sub: every protected-area outline cut into pieces of at most 128 vertices.

Run after the protected-area loaders. Species protection figures use this table for their
point-in-polygon tests; the results are identical, only faster.

Usage: python scripts/phase11_subdivide_protected_areas.py
"""

from __future__ import annotations

import os
import time

import psycopg

from db_schema import ensure_schema


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
MAX_VERTICES = 128


def main() -> None:
    started = time.monotonic()
    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE protected_areas_sub")
        connection.execute(
            """INSERT INTO protected_areas_sub (protected_area_id, pa_class, geom)
               SELECT protected_area_id, pa_class, ST_Subdivide(ST_MakeValid(geom), %s) FROM protected_areas""", (MAX_VERTICES,))
        connection.execute("ANALYZE protected_areas_sub")
        counts = connection.execute("SELECT pa_class, COUNT(*) FROM protected_areas_sub GROUP BY 1 ORDER BY 1").fetchall()
    print(f"protected_areas_sub rebuilt in {time.monotonic() - started:.0f}s: " + ", ".join(f"{name} {count:,}" for name, count in counts))


if __name__ == "__main__":
    main()
