"""Bring the PostGIS schema up to date with the Alembic migrations in backend/migrations."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "backend" / "alembic.ini"


def ensure_schema(database_url: str | None = None) -> None:
    from alembic import command
    from alembic.config import Config

    if database_url:
        os.environ["DATABASE_URL"] = database_url
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


if __name__ == "__main__":
    ensure_schema()
    print("Schema is at the latest migration.")
