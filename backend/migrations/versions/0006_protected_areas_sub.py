"""Phase 21: subdivided protected-area outlines for fast point-in-polygon tests.

Revision ID: 0006_protected_areas_sub
Revises: 0005_land_use_grid
Create Date: 2026-10-27
"""

from alembic import op


revision = "0006_protected_areas_sub"
down_revision = "0005_land_use_grid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        -- protected_areas cut into pieces of at most 128 vertices (scripts/phase11_subdivide_protected_areas.py).
        -- The reserved-forest layer alone has 42 million vertices; tests against small pieces are many times faster.
        CREATE TABLE IF NOT EXISTS protected_areas_sub (
            protected_area_id TEXT,
            pa_class TEXT,
            geom geometry
        );
        CREATE INDEX IF NOT EXISTS protected_areas_sub_geom_idx ON protected_areas_sub USING GIST (geom);
        CREATE INDEX IF NOT EXISTS protected_areas_sub_class_idx ON protected_areas_sub (pa_class);
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS protected_areas_sub")
