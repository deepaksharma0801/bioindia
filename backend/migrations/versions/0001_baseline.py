"""Baseline schema: species, occurrences, conservation assessments, land pressure, protected areas, grid analytics.

Written to be safe on a fresh database and on databases created before migrations existed
(every statement is IF NOT EXISTS), so `alembic upgrade head` adopts an existing database.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-26
"""

from alembic import op


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS species (
    species_id TEXT PRIMARY KEY,
    scientific_name TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    common_name TEXT,
    kingdom TEXT, phylum TEXT, class_name TEXT, order_name TEXT, family TEXT,
    genus TEXT, species_epithet TEXT,
    gbif_taxon_key BIGINT, iucn_taxon_id TEXT,
    native_status TEXT, endemic_status TEXT, environment_type TEXT,
    current_iucn_status TEXT,
    source TEXT NOT NULL, source_dataset_identifier TEXT NOT NULL, license TEXT
);

-- Where current_iucn_status came from. It is source-reported, not an official assessment;
-- verified categories live in conservation_assessments.
ALTER TABLE species ADD COLUMN IF NOT EXISTS current_iucn_status_source TEXT;

CREATE TABLE IF NOT EXISTS occurrences (
    occurrence_id TEXT PRIMARY KEY,
    species_id TEXT NOT NULL REFERENCES species(species_id),
    scientific_name_original TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
    coordinate_uncertainty DOUBLE PRECISION,
    event_date DATE NOT NULL, year SMALLINT NOT NULL, month SMALLINT,
    state TEXT, basis_of_record TEXT, dataset_key TEXT NOT NULL,
    source TEXT NOT NULL, source_record_id TEXT NOT NULL UNIQUE
);

-- Many GBIF records give only a year or year-month, so event_date holds the first day of the
-- recorded period and date_precision says how much of it is real ('day', 'month', 'year').
ALTER TABLE occurrences ALTER COLUMN event_date DROP NOT NULL;
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS date_precision TEXT;
-- 'precise' (<= 1 km), 'moderate' (<= 10 km), 'coarse' (> 10 km, e.g. obscured sensitive species), 'unknown'.
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS coordinate_uncertainty_class TEXT;
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS quality_flags TEXT[];
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS gbif_issues TEXT[];
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS license TEXT;
ALTER TABLE occurrences ADD COLUMN IF NOT EXISTS source_download_doi TEXT;

CREATE INDEX IF NOT EXISTS occurrences_geom_gix ON occurrences USING GIST (geom);
CREATE INDEX IF NOT EXISTS occurrences_uncertainty_class_idx ON occurrences (coordinate_uncertainty_class);
CREATE INDEX IF NOT EXISTS occurrences_species_year_idx ON occurrences (species_id, year);
CREATE INDEX IF NOT EXISTS occurrences_state_idx ON occurrences (state) WHERE state IS NOT NULL;

CREATE TABLE IF NOT EXISTS conservation_assessments (
    assessment_id TEXT PRIMARY KEY,
    species_id TEXT NOT NULL REFERENCES species(species_id),
    iucn_taxon_id TEXT,
    iucn_category TEXT NOT NULL,
    assessment_year SMALLINT NOT NULL,
    population_trend TEXT,
    threat_codes JSONB,
    threat_descriptions JSONB,
    habitat_codes JSONB,
    conservation_actions JSONB,
    assessment_version TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    dataset_version TEXT,
    retrieval_date DATE NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (species_id, assessment_version, source_url)
);

CREATE INDEX IF NOT EXISTS conservation_assessments_species_year_idx
    ON conservation_assessments (species_id, assessment_year DESC);

CREATE TABLE IF NOT EXISTS occurrence_land_pressure (
    occurrence_id TEXT PRIMARY KEY REFERENCES occurrences(occurrence_id),
    land_cover_class TEXT NOT NULL,
    land_cover_year SMALLINT NOT NULL,
    tree_cover_percent DOUBLE PRECISION,
    tree_cover_loss_year SMALLINT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieval_date DATE NOT NULL,
    spatial_resolution_m DOUBLE PRECISION NOT NULL,
    license TEXT
);

CREATE INDEX IF NOT EXISTS occurrence_land_pressure_loss_year_idx
    ON occurrence_land_pressure (tree_cover_loss_year) WHERE tree_cover_loss_year IS NOT NULL;

CREATE TABLE IF NOT EXISTS protected_areas (
    protected_area_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    designation TEXT,
    state_name TEXT,
    reported_area DOUBLE PRECISION,
    source TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL
);

-- pa_class: 'wildlife_pa' (OSM National Parks, Wildlife Sanctuaries, Conservation/Community
-- Reserves; the main protection layer), 'tiger_reserve' (OSM, includes buffers), and the WDPA
-- layers 'forest' and 'other_designation', which are reported separately. WDPA-only columns
-- are null for OSM rows.
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS pa_class TEXT NOT NULL DEFAULT 'unclassified';
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS wdpa_site_id TEXT;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS designation_type TEXT;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS status_year SMALLINT;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS realm TEXT;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS gis_area_km2 DOUBLE PRECISION;
ALTER TABLE protected_areas ADD COLUMN IF NOT EXISTS source_version TEXT;

CREATE INDEX IF NOT EXISTS protected_areas_geom_gix ON protected_areas USING GIST (geom);

-- Precomputed Phase 13 grid metrics (scripts/phase13_build_grid_metrics.py). Components are kept
-- separate; no composite score is stored.
CREATE TABLE IF NOT EXISTS analytics_grid_cells (
    cell_id TEXT PRIMARY KEY,
    grid_size_degrees DOUBLE PRECISION NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL,
    dominant_state TEXT,
    record_count INTEGER NOT NULL,
    records_within_10_km INTEGER NOT NULL,
    observed_species INTEGER NOT NULL,
    observed_species_within_10_km INTEGER NOT NULL,
    species_ids TEXT[] NOT NULL,
    threatened_species INTEGER NOT NULL,
    threatened_species_ids TEXT[] NOT NULL,
    threatened_status_verified BOOLEAN NOT NULL,
    years_with_records INTEGER NOT NULL,
    first_year SMALLINT,
    last_year SMALLINT,
    recent_records INTEGER NOT NULL,
    dataset_count INTEGER NOT NULL,
    wildlife_pa_pct DOUBLE PRECISION NOT NULL,
    tiger_reserve_pct DOUBLE PRECISION NOT NULL,
    forest_pct DOUBLE PRECISION NOT NULL,
    other_designation_pct DOUBLE PRECISION NOT NULL,
    built_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS analytics_grid_cells_geom_gix ON analytics_grid_cells USING GIST (geom);
CREATE INDEX IF NOT EXISTS protected_areas_pa_class_idx ON protected_areas (pa_class);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA_SQL)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "DROP TABLE IF EXISTS analytics_grid_cells, occurrence_land_pressure, conservation_assessments, "
        "occurrences, protected_areas, species CASCADE"
    )
