"""Phases 14-15: serve the current extinction-vulnerability model's predictions, explanations and metrics."""

from __future__ import annotations

from typing import Any

from .db import fetch_all


DISCLAIMER = "MODEL PREDICTION - not an official IUCN Red List assessment."
EXPLANATION_NOTE = "SHAP contributions show how each feature moved this model's prediction; they do not establish ecological causes."
FEATURE_DESCRIPTIONS = {
    "log_records": "log of GBIF records in India",
    "states_occupied": "states and union territories with records",
    "log_districts_occupied": "log of districts with records (range-size proxy)",
    "top_district_share": "share of records in the single busiest district (concentration)",
    "years_with_records": "number of years with any record",
    "first_record_year": "earliest record year",
    "last_record_year": "most recent record year",
    "recent_record_share": "share of records from 2016 onwards",
    "recent_vs_earlier_log_ratio": "log ratio of records 2016+ to 2006-2015 (recording trend, not abundance)",
    "specimen_share": "share of museum/collection records",
    "log_datasets": "log of contributing datasets",
    "log_occupied_cells_50km": "log of ~50 km grid cells with records (range-size proxy, robust to blurred locations)",
    "log_eoo_km2": "log of the convex-hull area around all records (extent-of-occurrence proxy)",
    "wildlife_pa_record_share": "share of precisely located records inside wildlife protected areas",
    "temperature_niche_breadth_c": "spread of annual mean temperature at records (90th minus 10th percentile)",
    "log_precipitation_niche_breadth_mm": "log spread of annual precipitation at records",
    "mean_elevation_m": "mean elevation of records",
    "forest_2000_share_occupied_cells": "tree cover in 2000 in the ~5 km cells with records",
    "recent_forest_loss_share_occupied_cells": "tree-cover loss 2015-2024 (share of 2000 tree cover) in the ~5 km cells with records",
    "built_up_share_occupied_cells": "built-up share of land in the ~5 km cells with records (human pressure)",
}


def describe(feature: str) -> str:
    if feature in FEATURE_DESCRIPTIONS:
        return FEATURE_DESCRIPTIONS[feature]
    if feature.startswith("group_"):
        return "taxonomic group: " + feature.removeprefix("group_").replace("_", " ")
    return feature.replace("_", " ")


def current_model() -> dict[str, Any] | None:
    rows = fetch_all("SELECT * FROM model_registry WHERE is_current ORDER BY trained_at DESC LIMIT 1")
    return rows[0] if rows else None


def model_info() -> dict[str, Any] | None:
    model = current_model()
    if model is None:
        return None
    return {
        "model_version": model["model_version"],
        "model_type": model["model_type"],
        "target": model["target"],
        "trained_at": model["trained_at"].isoformat(),
        "features": [{"name": name, "description": describe(name)} for name in model["features"]],
        "training_data": model["training_data"],
        "disclaimer": DISCLAIMER,
    }


def model_performance() -> dict[str, Any] | None:
    model = current_model()
    if model is None:
        return None
    return {"model_version": model["model_version"], **model["metrics"], "disclaimer": DISCLAIMER}


def prediction_ranking(limit: int, unlabelled_only: bool) -> dict[str, Any] | None:
    model = current_model()
    if model is None:
        return None
    rows = fetch_all(
        """SELECT p.species_id, s.common_name, s.scientific_name, s.class_name, p.predicted_probability, p.prediction_type,
                  p.shap_contributions, s.current_iucn_status AS reported_category,
                  (SELECT ca.iucn_category FROM conservation_assessments AS ca WHERE ca.species_id = s.species_id
                   ORDER BY ca.assessment_year DESC LIMIT 1) AS official_iucn_category
           FROM species_risk_predictions AS p JOIN species AS s ON s.species_id = p.species_id
           WHERE p.model_version = %(version)s AND (NOT %(unlabelled)s OR p.prediction_type = 'unlabelled')
           ORDER BY p.predicted_probability DESC LIMIT %(limit)s""",
        {"version": model["model_version"], "unlabelled": unlabelled_only, "limit": limit},
    )
    selected = model["metrics"]["selected_model"]
    return {
        "model_version": model["model_version"],
        "model_performance": {"pr_auc": model["metrics"]["candidates"][selected]["pr_auc"], "roc_auc": model["metrics"]["candidates"][selected]["roc_auc"],
                              "pr_auc_baseline": model["metrics"]["pr_auc_baseline_prevalence"]},
        "species": [{**row, "top_contributions": [{"feature": name, "description": describe(name), "shap_value": value}
                                                   for name, value in (row.pop("shap_contributions") or {}).items()]} for row in rows],
        "disclaimer": DISCLAIMER,
    }


def species_prediction(species_id: str, with_explanation: bool = False) -> dict[str, Any] | None:
    rows = fetch_all(
        """SELECT p.*, s.common_name, s.scientific_name,
                  (SELECT ca.iucn_category FROM conservation_assessments AS ca WHERE ca.species_id = s.species_id
                   ORDER BY ca.assessment_year DESC LIMIT 1) AS official_iucn_category
           FROM species_risk_predictions AS p
           JOIN model_registry AS m ON m.model_version = p.model_version AND m.is_current
           JOIN species AS s ON s.species_id = p.species_id
           WHERE p.species_id = %(id)s""",
        {"id": species_id},
    )
    if not rows:
        return None
    row = rows[0]
    payload = {
        "species_id": species_id,
        "common_name": row["common_name"],
        "scientific_name": row["scientific_name"],
        "model_version": row["model_version"],
        "predicted_threatened_probability": row["predicted_probability"],
        "prediction_type": row["prediction_type"],
        "prediction_type_note": ("scored by a cross-validation model that did not see this species" if row["prediction_type"] == "out_of_fold"
                                 else "species not used in training (Data Deficient or no verified assessment)"),
        "official_iucn_category": row["official_iucn_category"],
        "disclaimer": DISCLAIMER,
    }
    if with_explanation:
        payload["features"] = row["features"]
        payload["top_contributions"] = [
            {"feature": name, "description": describe(name), "shap_value": value,
             "direction": "raises predicted risk" if value > 0 else "lowers predicted risk"}
            for name, value in (row["shap_contributions"] or {}).items()
        ]
        payload["explanation_note"] = EXPLANATION_NOTE
    return payload
