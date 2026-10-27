"""Phase 10: gridded forest cover, forest loss, fragmentation and human-pressure layers.

Revision ID: 0005_land_use_grid
Revises: 0004_risk_model
Create Date: 2026-10-27
"""

from alembic import op


revision = "0005_land_use_grid"
down_revision = "0004_risk_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        -- One row per 0.05-degree cell (ix = floor(longitude * 20), iy = floor(latitude * 20)) attributed to an
        -- Indian state. Areas are in km2. Forest = Hansen tree cover >= 30 percent in 2000; loss is counted only inside
        -- that forest. Built-up area and population are GHSL 2020 estimates.
        CREATE TABLE IF NOT EXISTS land_use_cells (
            ix INTEGER NOT NULL,
            iy INTEGER NOT NULL,
            geom geometry(Polygon, 4326) NOT NULL,
            state TEXT,
            land_km2 DOUBLE PRECISION NOT NULL,
            forest_2000_km2 DOUBLE PRECISION NOT NULL,
            forest_loss_km2 DOUBLE PRECISION NOT NULL,
            forest_loss_km2_by_year DOUBLE PRECISION[] NOT NULL,
            forest_edge_share DOUBLE PRECISION,
            built_up_km2 DOUBLE PRECISION,
            population DOUBLE PRECISION,
            PRIMARY KEY (ix, iy)
        );
        CREATE INDEX IF NOT EXISTS land_use_cells_geom_idx ON land_use_cells USING GIST (geom);
        CREATE INDEX IF NOT EXISTS land_use_cells_state_idx ON land_use_cells (state);

        -- Mean land-use conditions over the 0.05-degree cells a species occupies (records within 10 km only),
        -- so heavily recorded places do not dominate. Loss shares are relative to year-2000 forest.
        CREATE TABLE IF NOT EXISTS species_land_pressure (
            species_id TEXT PRIMARY KEY REFERENCES species(species_id),
            sampled_records INTEGER NOT NULL,
            occupied_cells INTEGER NOT NULL,
            records_left_out JSONB NOT NULL,
            forest_2000_share DOUBLE PRECISION,
            forest_loss_share DOUBLE PRECISION,
            recent_forest_loss_share DOUBLE PRECISION,
            occupied_cells_with_loss_share DOUBLE PRECISION,
            forest_edge_share DOUBLE PRECISION,
            built_up_share DOUBLE PRECISION,
            population_density_per_km2 DOUBLE PRECISION
        );

        ALTER TABLE analytics_grid_cells
            ADD COLUMN IF NOT EXISTS forest_2000_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS forest_loss_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS recent_forest_loss_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS forest_edge_share DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS built_up_pct DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS population_density_per_km2 DOUBLE PRECISION;
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        ALTER TABLE analytics_grid_cells
            DROP COLUMN IF EXISTS forest_2000_pct, DROP COLUMN IF EXISTS forest_loss_pct,
            DROP COLUMN IF EXISTS recent_forest_loss_pct, DROP COLUMN IF EXISTS forest_edge_share,
            DROP COLUMN IF EXISTS built_up_pct, DROP COLUMN IF EXISTS population_density_per_km2;
        DROP TABLE IF EXISTS species_land_pressure, land_use_cells;
    """)
