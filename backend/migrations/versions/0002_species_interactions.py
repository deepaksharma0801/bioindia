"""Phase 16: documented species interactions (GloBI).

Revision ID: 0002_species_interactions
Revises: 0001_baseline
Create Date: 2026-10-26
"""

from alembic import op


revision = "0002_species_interactions"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS species_interactions (
            interaction_id TEXT PRIMARY KEY,
            source_taxon_name TEXT NOT NULL,
            source_species_id TEXT REFERENCES species(species_id),
            interaction_type TEXT NOT NULL,
            target_taxon_name TEXT NOT NULL,
            target_species_id TEXT REFERENCES species(species_id),
            target_taxon_path TEXT,
            -- 'DOCUMENTED' for reported interactions; 'CO_OCCURRENCE_ASSOCIATION' for co-occurrence,
            -- which is never treated as an ecological interaction.
            evidence_type TEXT NOT NULL,
            reference TEXT,
            dataset_citation TEXT,
            study_url TEXT,
            data_source TEXT NOT NULL,
            retrieved_at DATE NOT NULL
        );
        CREATE INDEX IF NOT EXISTS species_interactions_source_idx ON species_interactions (source_species_id);
        CREATE INDEX IF NOT EXISTS species_interactions_target_idx ON species_interactions (target_species_id);
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS species_interactions")
