"""Record which taxon an IUCN assessment covers (species, subspecies or regional subpopulation).

Revision ID: 0003_assessment_taxon_level
Revises: 0002_species_interactions
Create Date: 2026-10-27
"""

from alembic import op


revision = "0003_assessment_taxon_level"
down_revision = "0002_species_interactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        ALTER TABLE conservation_assessments ADD COLUMN IF NOT EXISTS assessed_taxon_name TEXT;
        -- 'species', 'subspecies' or 'subpopulation'. Infraspecific assessments describe the Indian
        -- taxon, not the species' global status, and are labelled as such.
        ALTER TABLE conservation_assessments ADD COLUMN IF NOT EXISTS taxon_level TEXT NOT NULL DEFAULT 'species';
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("""
        ALTER TABLE conservation_assessments DROP COLUMN IF EXISTS taxon_level;
        ALTER TABLE conservation_assessments DROP COLUMN IF EXISTS assessed_taxon_name;
    """)
