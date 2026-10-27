"""Phases 18-19: experimental research indices IBVCI (per species) and CIPI (per grid cell).

Both are EXPERIMENTAL METRICS DEVELOPED IN THIS PROJECT, not established standards.
  * Every component is scaled to 0-1 by percentile rank and returned separately.
  * Weights are never fixed by the platform: the default is an unweighted mean (a neutral reference,
    not a recommendation) and callers can pass their own. Missing components are left out of an
    item's composite and listed, never filled in.
  * A sensitivity analysis draws random weights (Dirichlet(1)) many times and reports each item's
    median rank and 5th-95th percentile rank, so rankings that depend on the weighting are visible.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .db import fetch_all
from .land_pressure import all_species_land_pressure


SENSITIVITY_DRAWS = 1000
SEED = 20261027
THREATENED = ("CR", "EN", "VU")

IBVCI_COMPONENTS = {
    "extinction_vulnerability": "model-predicted probability of threatened status (Phase 14)",
    "climate_niche_narrowness": "narrow temperature niche at precisely located records (climate-sensitivity proxy, not exposure)",
    "range_restriction": "few ~50 km cells with records (range-size proxy)",
    "recording_decline": "fewer records 2016+ than 2006-2015 (recording-trend proxy, not abundance)",
    "network_importance": "documented interaction partners (GloBI)",
    "protection_deficit": "share of precisely located records outside wildlife protected areas",
    "habitat_loss": "tree-cover loss 2015-2024 relative to year-2000 forest in the cells the species occupies (Hansen GFC)",
    "human_pressure": "built-up share of land in the cells the species occupies (GHSL 2020)",
}
CIPI_COMPONENTS = {
    "biodiversity_value": "observed tracked species in the cell",
    "threatened_concentration": "threatened species in the cell",
    "vulnerability": "mean model-predicted vulnerability of species in the cell",
    "ecological_importance": "mean documented interaction partners of species in the cell",
    "coverage_gap": "share of the cell outside wildlife protected areas",
    "habitat_loss": "tree-cover loss 2015-2024 relative to year-2000 forest in the cell (Hansen GFC)",
    "human_pressure": "built-up share of the cell's land (GHSL 2020)",
}
UNAVAILABLE: dict[str, str] = {}
CAVEATS = [
    "Experimental metric developed within this project; not an established or official index.",
    "Components overlap (e.g. the vulnerability model already uses range and protection features), so the composite double-counts some signals.",
    "Occurrence-based components reflect recording effort as well as ecology.",
    "Tree-cover loss includes plantation harvest and natural disturbance; it is pressure on places, not a measured effect on species.",
]


class IndexError_(ValueError):
    """Invalid index request (unknown component in weights, unknown item)."""


def percentile_rank(values: np.ndarray, invert: bool = False) -> np.ndarray:
    """0-1 rank of each value among the non-missing values; NaN stays NaN."""
    result = np.full(len(values), np.nan)
    mask = ~np.isnan(values)
    if mask.sum() == 0:
        return result
    order = values[mask].argsort().argsort().astype(float)
    ranks = order / (mask.sum() - 1) if mask.sum() > 1 else np.zeros(1)
    result[mask] = 1 - ranks if invert else ranks
    return result


def parse_weights(text: str | None, components: dict[str, str]) -> dict[str, float]:
    if not text:
        return {name: 1.0 for name in components}
    weights = {}
    for part in text.split(","):
        name, _, value = part.partition(":")
        name = name.strip()
        if name not in components:
            raise IndexError_(f"Unknown component '{name}'. Components: {', '.join(components)}.")
        try:
            weights[name] = float(value)
        except ValueError as error:
            raise IndexError_(f"Weight for '{name}' must be a number.") from error
        if weights[name] < 0:
            raise IndexError_("Weights must not be negative.")
    if not any(weights.values()):
        raise IndexError_("At least one weight must be positive.")
    return weights


MIN_COMPONENT_SHARE = 2 / 3


def composite(matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted mean over available components per row (missing components drop out).

    Rows with fewer than two-thirds of the components get no composite: ranking them on a
    subset would not be comparable with fully described rows.
    """
    available = ~np.isnan(matrix)
    weighted = np.where(available, matrix, 0.0) @ weights
    totals = available.astype(float) @ weights
    enough = available.sum(axis=1) >= np.ceil(MIN_COMPONENT_SHARE * matrix.shape[1])
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((totals > 0) & enough, weighted / totals, np.nan)


def sensitivity(matrix: np.ndarray) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(SEED)
    ranks = np.empty((SENSITIVITY_DRAWS, matrix.shape[0]))
    for draw in range(SENSITIVITY_DRAWS):
        scores = composite(matrix, rng.dirichlet(np.ones(matrix.shape[1])))
        ranks[draw] = (-np.nan_to_num(scores, nan=-1)).argsort().argsort() + 1
    return {"median": np.median(ranks, axis=0), "p05": np.percentile(ranks, 5, axis=0), "p95": np.percentile(ranks, 95, axis=0),
            "top10_share": (ranks <= 10).mean(axis=0)}


def _ranked(ids: list[str], matrix: np.ndarray, components: dict[str, str], weights: dict[str, float], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    weight_vector = np.array([weights.get(name, 0.0) for name in components])
    scores = composite(matrix, weight_vector)
    spread = sensitivity(matrix)
    order = (-np.nan_to_num(scores, nan=-1)).argsort()
    items = []
    for rank, position in enumerate(order, start=1):
        row = matrix[position]
        insufficient = bool(np.isnan(scores[position]))
        items.append({
            **extra[position],
            "rank": None if insufficient else rank,
            "insufficient_data": insufficient,
            "composite": None if np.isnan(scores[position]) else round(float(scores[position]), 4),
            "components": {name: None if np.isnan(row[i]) else round(float(row[i]), 4) for i, name in enumerate(components)},
            "missing_components": [name for i, name in enumerate(components) if np.isnan(row[i])],
            "sensitivity": {"median_rank": float(spread["median"][position]), "rank_p05": float(spread["p05"][position]),
                            "rank_p95": float(spread["p95"][position]), "share_of_draws_in_top_10": round(float(spread["top10_share"][position]), 3)},
        })
    return items


def _partner_counts() -> dict[str, int]:
    rows = fetch_all("""
        SELECT species_id, COUNT(DISTINCT partner) AS partners FROM (
            SELECT source_species_id AS species_id, target_taxon_name AS partner FROM species_interactions WHERE evidence_type = 'DOCUMENTED'
            UNION ALL SELECT target_species_id, source_taxon_name FROM species_interactions WHERE evidence_type = 'DOCUMENTED') AS links
        WHERE species_id IS NOT NULL GROUP BY species_id""")
    return {row["species_id"]: row["partners"] for row in rows}


def _predictions() -> dict[str, dict[str, Any]]:
    rows = fetch_all("""
        SELECT p.species_id, p.predicted_probability, p.features FROM species_risk_predictions AS p
        JOIN model_registry AS m ON m.model_version = p.model_version AND m.is_current""")
    return {row["species_id"]: row for row in rows}


def _number(value: Any) -> float:
    return np.nan if value is None else float(value)


def _metadata(components: dict[str, str], weights: dict[str, float], custom: bool) -> dict[str, Any]:
    return {
        "label": "EXPERIMENTAL RESEARCH METRIC",
        "components": components,
        "unavailable_components": UNAVAILABLE,
        "weights": weights,
        "weights_note": "Custom weights supplied by the caller." if custom else "Unweighted mean: a neutral reference, not derived from literature or data. Pass weights=name:value,... to explore alternatives.",
        "scaling": "each component is a 0-1 percentile rank among items with data",
        "minimum_components": f"a composite needs at least {MIN_COMPONENT_SHARE:.0%} of the components; others are listed with insufficient_data and no rank",
        "sensitivity": f"{SENSITIVITY_DRAWS} random weightings (Dirichlet(1)); ranks are 1 = highest composite",
        "caveats": CAVEATS,
    }


def ibvci(weights_text: str | None = None, limit: int = 50, species_id: str | None = None) -> dict[str, Any] | None:
    weights = parse_weights(weights_text, IBVCI_COMPONENTS)
    species = fetch_all("SELECT species_id, common_name, scientific_name FROM species ORDER BY species_id")
    predictions, partners, land = _predictions(), _partner_counts(), all_species_land_pressure()
    if not predictions:
        return None
    ids = [row["species_id"] for row in species]

    def feature(name: str) -> np.ndarray:
        return np.array([float((predictions.get(i, {}).get("features") or {}).get(name)) if (predictions.get(i, {}).get("features") or {}).get(name) is not None else np.nan for i in ids])

    probability = np.array([predictions[i]["predicted_probability"] if i in predictions else np.nan for i in ids])
    pa_share = feature("wildlife_pa_record_share")
    matrix = np.column_stack([
        percentile_rank(probability),
        percentile_rank(feature("temperature_niche_breadth_c"), invert=True),
        percentile_rank(feature("log_occupied_cells_50km"), invert=True),
        percentile_rank(feature("recent_vs_earlier_log_ratio"), invert=True),
        percentile_rank(np.array([float(partners.get(i, 0)) for i in ids])),
        percentile_rank(1 - pa_share),
        percentile_rank(np.array([_number(land.get(i, {}).get("recent_forest_loss_share")) for i in ids])),
        percentile_rank(np.array([_number(land.get(i, {}).get("built_up_share")) for i in ids])),
    ])
    items = _ranked(ids, matrix, IBVCI_COMPONENTS, weights, [{"species_id": row["species_id"], "common_name": row["common_name"], "scientific_name": row["scientific_name"]} for row in species])
    if species_id:
        match = [item for item in items if item["species_id"] == species_id]
        if not match:
            raise IndexError_(f"Species '{species_id}' was not found.")
        items = match
    return {"index": "IBVCI - Indian Biodiversity Vulnerability and Cascade Index", **_metadata(IBVCI_COMPONENTS, weights, bool(weights_text)),
            "items_ranked": len(ids), "species": items[:limit]}


def cipi(weights_text: str | None = None, limit: int = 50, state: str | None = None) -> dict[str, Any] | None:
    weights = parse_weights(weights_text, CIPI_COMPONENTS)
    cells = fetch_all("""SELECT cell_id, dominant_state, species_ids, observed_species, threatened_species, wildlife_pa_pct, record_count,
                                recent_forest_loss_pct, built_up_pct,
                                ST_Y(ST_Centroid(geom)) AS centroid_lat, ST_X(ST_Centroid(geom)) AS centroid_lon
                         FROM analytics_grid_cells ORDER BY cell_id""")
    if not cells:
        return None
    predictions, partners = _predictions(), _partner_counts()

    def mean_over(cell: dict[str, Any], values: dict[str, float]) -> float:
        found = [values[s] for s in cell["species_ids"] if s in values]
        return float(np.mean(found)) if found else np.nan

    probability = {key: value["predicted_probability"] for key, value in predictions.items()}
    matrix = np.column_stack([
        percentile_rank(np.array([float(c["observed_species"]) for c in cells])),
        percentile_rank(np.array([float(c["threatened_species"]) for c in cells])),
        percentile_rank(np.array([mean_over(c, probability) for c in cells])),
        percentile_rank(np.array([mean_over(c, {k: float(v) for k, v in partners.items()}) for c in cells])),
        percentile_rank(np.array([1 - float(c["wildlife_pa_pct"]) / 100 for c in cells])),
        percentile_rank(np.array([_number(c["recent_forest_loss_pct"]) for c in cells])),
        percentile_rank(np.array([_number(c["built_up_pct"]) for c in cells])),
    ])
    extra = [{"cell_id": c["cell_id"], "dominant_state": c["dominant_state"], "centroid_lat": round(c["centroid_lat"], 3),
              "centroid_lon": round(c["centroid_lon"], 3), "record_count": c["record_count"]} for c in cells]
    items = _ranked([c["cell_id"] for c in cells], matrix, CIPI_COMPONENTS, weights, extra)
    if state:
        items = [item for item in items if item["dominant_state"] == state]
    return {"index": "CIPI - Conservation Intervention Priority Index", **_metadata(CIPI_COMPONENTS, weights, bool(weights_text)),
            "items_ranked": len(cells), "data_sufficiency_note": "record_count shows how much data each cell rests on; low-record cells are less reliable.",
            "cells": items[:limit]}
