"""Phase 10: forest cover, forest loss, fragmentation and human pressure from the 0.05-degree land-use grid."""

from __future__ import annotations

from typing import Any

from .db import fetch_all


LOSS_YEARS = list(range(2001, 2025))
RECENT_FROM = 2015
METADATA = {
    "sources": {
        "forest": "Hansen et al. (2013) Global Forest Change 2000-2024 v1.12 (University of Maryland), 30 m, CC BY 4.0",
        "built_up_and_population": "GHSL R2023A GHS-BUILT-S and GHS-POP, epoch 2020, 30 arc-seconds (European Commission JRC), CC BY 4.0",
    },
    "spatial_resolution": "aggregated to 0.05-degree cells (about 5.5 km)",
    "forest_definition": "tree canopy cover of at least 30% in 2000; includes plantations and orchards, so it is tree cover, not natural forest",
    "loss_definition": "stand-replacing tree-cover loss inside year-2000 forest, 2001-2024; regrowth (gain) is not subtracted",
    "fragmentation_definition": "forest edge share: share of year-2000 forest pixels with a non-forest neighbour (higher = more fragmented)",
    "limitations": "Tree-cover loss includes plantation harvest and natural disturbance as well as clearing. Values describe places, "
                   "not effects on any species; association is not causation. Population and built-up area are 2020 estimates only.",
}


def species_land_pressure(species_id: str) -> dict[str, Any] | None:
    rows = fetch_all("SELECT * FROM species_land_pressure WHERE species_id = %(id)s", {"id": species_id})
    if not rows:
        return None
    profile = rows[0]
    return {
        "profile": profile,
        "metadata": {**METADATA, "method": "Mean over the 0.05-degree cells the species occupies, using records located within 10 km; "
                                           "each occupied cell counts once, so heavily recorded places do not dominate. "
                                           "Loss shares are relative to year-2000 forest in those cells."},
    }


def all_species_land_pressure() -> dict[str, dict[str, Any]]:
    return {row["species_id"]: row for row in fetch_all("SELECT * FROM species_land_pressure")}


STATE_SQL = """
SELECT state, COUNT(*) AS cells, SUM(land_km2) AS land_km2, SUM(forest_2000_km2) AS forest_2000_km2,
       SUM(forest_loss_km2) AS forest_loss_km2,
       SUM(forest_edge_share * forest_2000_km2) / NULLIF(SUM(forest_2000_km2) FILTER (WHERE forest_edge_share IS NOT NULL), 0) AS forest_edge_share,
       SUM(built_up_km2) AS built_up_km2, SUM(population) AS population,
       (SELECT ARRAY_AGG(total ORDER BY year_index) FROM (
            SELECT ordinality AS year_index, SUM(value) AS total
            FROM land_use_cells AS inner_cells, unnest(inner_cells.forest_loss_km2_by_year) WITH ORDINALITY AS loss(value, ordinality)
            WHERE inner_cells.state = c.state GROUP BY ordinality) AS yearly) AS loss_by_year
FROM land_use_cells AS c
WHERE (%(state)s::text IS NULL OR lower(state) = lower(%(state)s))
GROUP BY state ORDER BY state
"""


def _state_summary(row: dict[str, Any], with_series: bool) -> dict[str, Any]:
    forest, land, loss = row["forest_2000_km2"], row["land_km2"], row["forest_loss_km2"]
    series = row["loss_by_year"] or []
    recent = sum(series[RECENT_FROM - LOSS_YEARS[0]:])
    summary = {
        "state": row["state"],
        "land_km2": round(land),
        "forest_2000_km2": round(forest),
        "forest_2000_pct_of_land": round(100 * forest / land, 2) if land else None,
        "forest_loss_2001_2024_km2": round(loss, 1),
        "forest_loss_pct_of_2000_forest": round(100 * loss / forest, 2) if forest else None,
        "recent_forest_loss_2015_2024_pct": round(100 * recent / forest, 2) if forest else None,
        "forest_edge_share": round(row["forest_edge_share"], 3) if row["forest_edge_share"] is not None else None,
        "built_up_pct_of_land": round(100 * row["built_up_km2"] / land, 2) if land else None,
        "population_2020": round(row["population"]),
        "population_density_per_km2": round(row["population"] / land, 1) if land else None,
    }
    if with_series:
        summary["forest_loss_km2_by_year"] = {str(year): round(value, 2) for year, value in zip(LOSS_YEARS, series)}
    return summary


def state_land_use(state: str | None = None) -> dict[str, Any] | None:
    rows = fetch_all(STATE_SQL, {"state": state})
    if not rows:
        return None
    if state is not None:
        return {**_state_summary(rows[0], with_series=True), "metadata": METADATA}
    return {"states": [_state_summary(row, with_series=False) for row in rows], "metadata": METADATA}
