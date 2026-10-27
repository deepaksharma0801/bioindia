"""Phase 14-15: extinction-vulnerability model registry, predictions and SHAP explanations.

Revision ID: 0004_risk_model
Revises: 0003_assessment_taxon_level
Create Date: 2026-10-27
"""

from alembic import op


revision = "0004_risk_model"
down_revision = "0003_assessment_taxon_level"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS model_registry (
            model_version TEXT PRIMARY KEY,
            model_type TEXT NOT NULL,
            target TEXT NOT NULL,
            features JSONB NOT NULL,
            metrics JSONB NOT NULL,
            training_data JSONB NOT NULL,
            trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            artifact_path TEXT,
            is_current BOOLEAN NOT NULL DEFAULT FALSE
        );
        -- Model output, never an official IUCN assessment. prediction_type is 'out_of_fold' for
        -- species used in training (scored by a model that did not see them) or 'unlabelled'.
        CREATE TABLE IF NOT EXISTS species_risk_predictions (
            model_version TEXT NOT NULL REFERENCES model_registry(model_version) ON DELETE CASCADE,
            species_id TEXT NOT NULL REFERENCES species(species_id),
            predicted_probability DOUBLE PRECISION NOT NULL,
            prediction_type TEXT NOT NULL,
            training_label SMALLINT,
            features JSONB NOT NULL,
            shap_contributions JSONB,
            PRIMARY KEY (model_version, species_id)
        );
    """)


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS species_risk_predictions, model_registry")
