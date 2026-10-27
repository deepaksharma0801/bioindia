"""Alembic environment: runs migrations against DATABASE_URL with the psycopg 3 driver."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool


DEFAULT_DATABASE_URL = "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia"


def database_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url


def run_migrations_offline() -> None:
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
