"""Phase 14-15: extinction-vulnerability model with SHAP explanations.

Target: official IUCN category threatened (CR/EN/VU) = 1 vs not threatened (LC/NT) = 0. Data
Deficient species and species without a verified assessment (the flagships) are not used for
training; they receive predictions. Features come only from GBIF occurrence summaries (range,
recording history, record types) and taxonomic group, never from IUCN assessment content, so
the model cannot read its own label.

Evaluation: repeated stratified 5-fold cross-validation; ROC-AUC, PR-AUC, precision, recall, F1,
Brier score and a reliability table. The model with the best mean PR-AUC is refitted on all
labelled species. Predictions for training species are out-of-fold (made by models that did not
see them). SHAP values explain model behaviour, not ecological causes.

Outputs: models/trained/<version>.joblib, data/analytics/risk_model_report.json,
         model_registry and species_risk_predictions tables.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
SUMMARIES = ROOT / "data" / "processed" / "gbif_species_summaries.json"
MODELS = ROOT / "models" / "trained"
REPORT = ROOT / "data" / "analytics" / "risk_model_report.json"
CLIMATE = ROOT / "data" / "analytics" / "species_climate_profiles.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
SEED = 20261027
THREATENED = {"CR", "EN", "VU"}
NOT_THREATENED = {"LC", "NT"}
RECENT_FROM, EARLIER_FROM = 2016, 2006
GROUPS = {"Aves": "birds", "Mammalia": "mammals", "Reptilia": "reptiles", "Amphibia": "amphibians",
          "Actinopterygii": "fishes", "Chondrichthyes": "fishes", "Elasmobranchii": "fishes"}
SPECIMEN_TYPES = {"PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "MATERIAL_CITATION", "FOSSIL_SPECIMEN", "LIVING_SPECIMEN"}


def group_of(kingdom: str | None, class_name: str | None) -> str:
    if (kingdom or "").lower() == "plantae":
        return "plants"
    return GROUPS.get(class_name or "", "other")


def summary_features(summary: dict) -> dict[str, float]:
    total = summary["count"]
    facets = summary["facets"]
    years = {int(year): count for year, count in facets.get("YEAR", {}).items() if year.isdigit()}
    districts = facets.get("GADM_LEVEL_2_GID", {})
    basis = facets.get("BASIS_OF_RECORD", {})
    recent = sum(count for year, count in years.items() if year >= RECENT_FROM)
    earlier = sum(count for year, count in years.items() if EARLIER_FROM <= year < RECENT_FROM)
    return {
        "log_records": math.log1p(total),
        "states_occupied": len(facets.get("GADM_LEVEL_1_GID", {})),
        "log_districts_occupied": math.log1p(len(districts)),
        "top_district_share": max(districts.values()) / sum(districts.values()) if districts else np.nan,
        "years_with_records": len(years),
        "first_record_year": min(years) if years else np.nan,
        "last_record_year": max(years) if years else np.nan,
        "recent_record_share": recent / total if total else np.nan,
        "recent_vs_earlier_log_ratio": math.log((recent + 1) / (earlier + 1)),
        "specimen_share": sum(count for kind, count in basis.items() if kind in SPECIMEN_TYPES) / total if total else np.nan,
        "log_datasets": math.log1p(len(facets.get("DATASET_KEY", {}))),
    }


# Range from ALL records on a ~50 km grid: publishers blur threatened species by up to ~30 km, so a
# fine grid or a precise-records-only filter would make 'missing or blurred location' a proxy for
# 'threatened' (label leakage). Protected-area overlap genuinely needs precise points and stays
# precise-only; species without precise records get the median, and no missingness flag is used.
RANGE_FEATURES_SQL = """
    SELECT species_id,
           COUNT(DISTINCT (FLOOR(longitude * 2), FLOOR(latitude * 2))) AS occupied_cells_50km,
           ST_Area(ST_ConvexHull(ST_Collect(geom))::geography) / 1e6 AS eoo_km2
    FROM occurrences GROUP BY species_id
"""
PROTECTION_FEATURES_SQL = """
    SELECT o.species_id,
           AVG(CASE WHEN EXISTS (SELECT 1 FROM protected_areas AS pa
                                 WHERE pa.pa_class = 'wildlife_pa' AND ST_Intersects(pa.geom, o.geom)) THEN 1.0 ELSE 0.0 END) AS wildlife_pa_share
    FROM occurrences AS o
    WHERE o.coordinate_uncertainty_class IN ('precise', 'moderate')
    GROUP BY o.species_id
"""


def record_level_features() -> pd.DataFrame:
    """Range from all loaded records (coarse grid), protection and climate niche from records within 10 km."""
    with psycopg.connect(DATABASE_URL) as connection:
        ranges = pd.DataFrame(connection.execute(RANGE_FEATURES_SQL).fetchall(), columns=["species_id", "cells", "eoo_km2"]).set_index("species_id")
        protection = pd.DataFrame(connection.execute(PROTECTION_FEATURES_SQL).fetchall(), columns=["species_id", "pa_share"]).set_index("species_id")
    features = pd.DataFrame(index=ranges.index)
    features["log_occupied_cells_50km"] = np.log1p(ranges["cells"].astype(float))
    features["log_eoo_km2"] = np.log1p(ranges["eoo_km2"].astype(float))
    features = features.join(protection["pa_share"].astype(float).rename("wildlife_pa_record_share"), how="left")
    if CLIMATE.exists():
        profiles = pd.DataFrame(json.loads(CLIMATE.read_text(encoding="utf-8"))["profiles"]).set_index("species_id")
        features = features.join(pd.DataFrame({
            "temperature_niche_breadth_c": profiles["annual_mean_temperature_c_p90"] - profiles["annual_mean_temperature_c_p10"],
            "log_precipitation_niche_breadth_mm": np.log1p(profiles["annual_precipitation_mm_p90"] - profiles["annual_precipitation_mm_p10"]),
            "mean_elevation_m": profiles["elevation_m"],
        }), how="outer")
    return features


def build_table(include_record_features: bool = True) -> pd.DataFrame:
    summaries = {item["species_id"]: item for item in json.loads(SUMMARIES.read_text(encoding="utf-8"))}
    with psycopg.connect(DATABASE_URL) as connection:
        species = connection.execute("""
            SELECT s.species_id, s.kingdom, s.class_name,
                   (SELECT ca.iucn_category FROM conservation_assessments AS ca WHERE ca.species_id = s.species_id
                    ORDER BY ca.assessment_year DESC LIMIT 1) AS verified_category
            FROM species AS s ORDER BY s.species_id""").fetchall()
    rows = []
    for species_id, kingdom, class_name, category in species:
        if species_id not in summaries:
            continue
        label = 1 if category in THREATENED else 0 if category in NOT_THREATENED else None
        rows.append({"species_id": species_id, "verified_category": category, "label": label,
                     "group": group_of(kingdom, class_name), **summary_features(summaries[species_id])})
    table = pd.DataFrame(rows).set_index("species_id")
    table = pd.concat([table, pd.get_dummies(table["group"], prefix="group", dtype=float)], axis=1)
    if include_record_features:
        table = table.join(record_level_features(), how="left")
    return table


def candidate_models(positives: int, negatives: int) -> dict[str, Pipeline]:
    return {
        "logistic_regression": Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()),
                                         ("model", LogisticRegression(class_weight="balanced", C=0.5, max_iter=2000))]),
        "random_forest": Pipeline([("impute", SimpleImputer(strategy="median")),
                                   ("model", RandomForestClassifier(n_estimators=500, min_samples_leaf=3, class_weight="balanced_subsample", random_state=SEED))]),
        "xgboost": Pipeline([("impute", SimpleImputer(strategy="median")),
                             ("model", XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                                                     scale_pos_weight=negatives / max(positives, 1), eval_metric="logloss", random_state=SEED))]),
    }


def evaluate(model: Pipeline, features: pd.DataFrame, labels: pd.Series) -> dict[str, dict[str, float]]:
    scores: dict[str, list[float]] = {name: [] for name in ("roc_auc", "pr_auc", "precision", "recall", "f1", "brier")}
    splitter = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=SEED)
    for train, test in splitter.split(features, labels):
        fitted = clone(model).fit(features.iloc[train], labels.iloc[train])
        probability = fitted.predict_proba(features.iloc[test])[:, 1]
        predicted = (probability >= 0.5).astype(int)
        truth = labels.iloc[test]
        scores["roc_auc"].append(roc_auc_score(truth, probability))
        scores["pr_auc"].append(average_precision_score(truth, probability))
        scores["precision"].append(precision_score(truth, predicted, zero_division=0))
        scores["recall"].append(recall_score(truth, predicted, zero_division=0))
        scores["f1"].append(f1_score(truth, predicted, zero_division=0))
        scores["brier"].append(brier_score_loss(truth, probability))
    return {name: {"mean": round(float(np.mean(values)), 4), "sd": round(float(np.std(values)), 4)} for name, values in scores.items()}


def reliability(labels: pd.Series, probability: np.ndarray) -> list[dict[str, float]]:
    bins = np.linspace(0, 1, 6)
    table = []
    for low, high in zip(bins[:-1], bins[1:]):
        mask = (probability >= low) & (probability < high if high < 1 else probability <= high)
        if mask.any():
            table.append({"bin": f"{low:.1f}-{high:.1f}", "species": int(mask.sum()),
                          "mean_predicted": round(float(probability[mask].mean()), 3), "observed_threatened_share": round(float(labels[mask].mean()), 3)})
    return table


def shap_values(model: Pipeline, features: pd.DataFrame, background: pd.DataFrame, model_name: str) -> np.ndarray:
    import shap

    transformed = model[:-1].transform(features)
    if model_name == "logistic_regression":
        explainer = shap.LinearExplainer(model[-1], model[:-1].transform(background))
        return np.asarray(explainer.shap_values(transformed))
    values = shap.TreeExplainer(model[-1]).shap_values(transformed)
    values = values[1] if isinstance(values, list) else np.asarray(values)
    return values[..., 1] if values.ndim == 3 else values


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--summary-features-only", action="store_true", help="Skip record-level features from loaded occurrences.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = build_table(include_record_features=not args.summary_features_only)
    feature_columns = [c for c in table.columns if c not in {"verified_category", "label", "group"}]
    labelled = table[table["label"].notna()]
    unlabelled = table[table["label"].isna()]
    features, labels = labelled[feature_columns].astype(float), labelled["label"].astype(int)
    positives, negatives = int(labels.sum()), int((1 - labels).sum())

    models = candidate_models(positives, negatives)
    evaluation = {name: evaluate(model, features, labels) for name, model in models.items()}
    best_name = max(evaluation, key=lambda name: evaluation[name]["pr_auc"]["mean"])
    best = models[best_name]

    out_of_fold = cross_val_predict(clone(best), features, labels, cv=StratifiedKFold(5, shuffle=True, random_state=SEED), method="predict_proba")[:, 1]
    final = clone(best).fit(features, labels)
    unlabelled_probability = final.predict_proba(unlabelled[feature_columns].astype(float))[:, 1] if len(unlabelled) else np.array([])
    contributions = shap_values(final, table[feature_columns].astype(float), features, best_name)
    shap_frame = pd.DataFrame(contributions, index=table.index, columns=feature_columns)
    global_importance = shap_frame.loc[features.index].abs().mean().sort_values(ascending=False)

    trained_at = datetime.now(timezone.utc)
    version = f"risk_{best_name}_{trained_at:%Y%m%d%H%M}"
    MODELS.mkdir(parents=True, exist_ok=True)
    artifact = MODELS / f"{version}.joblib"
    joblib.dump({"model": final, "features": feature_columns}, artifact)

    metrics = {
        "cross_validation": "repeated stratified 5-fold, 5 repeats",
        "candidates": evaluation,
        "selected_model": best_name,
        "selection_rule": "highest mean PR-AUC",
        "pr_auc_baseline_prevalence": round(positives / len(labels), 4),
        "reliability_out_of_fold": reliability(labels, out_of_fold),
        "global_importance_mean_abs_shap": {name: round(float(value), 4) for name, value in global_importance.items()},
    }
    training_data = {
        "labelled_species": len(labels), "threatened": positives, "not_threatened": negatives,
        "unlabelled_species_predicted": len(unlabelled),
        "label_source": "conservation_assessments (IUCN Red List export retrieved 2026-10-21)",
        "feature_source": "GBIF occurrence search facets for India" + ("" if args.summary_features_only else
                          "; range from all loaded records on a ~50 km grid; protected-area and climate-niche features from records located within 10 km; no location-precision flag (leakage guard)"),
        "excluded_from_training": "Data Deficient species and species without a verified assessment",
    }
    rows = []
    for species_id, row in table.iterrows():
        in_training = species_id in features.index
        probability = out_of_fold[features.index.get_loc(species_id)] if in_training else unlabelled_probability[unlabelled.index.get_loc(species_id)]
        top = shap_frame.loc[species_id].sort_values(key=np.abs, ascending=False).head(5)
        rows.append({
            "model_version": version, "species_id": species_id, "predicted_probability": round(float(probability), 4),
            "prediction_type": "out_of_fold" if in_training else "unlabelled",
            "training_label": int(row["label"]) if in_training else None,
            "features": json.dumps({c: (None if pd.isna(row[c]) else round(float(row[c]), 4)) for c in feature_columns}),
            "shap_contributions": json.dumps({name: round(float(value), 4) for name, value in top.items()}),
        })

    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE model_registry SET is_current = FALSE")
            cursor.execute(
                """INSERT INTO model_registry (model_version, model_type, target, features, metrics, training_data, trained_at, artifact_path, is_current)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)""",
                (version, best_name, "IUCN threatened (CR/EN/VU) vs not threatened (LC/NT)", json.dumps(feature_columns),
                 json.dumps(metrics), json.dumps(training_data), trained_at, str(artifact.relative_to(ROOT))),
            )
            cursor.executemany(
                """INSERT INTO species_risk_predictions (model_version, species_id, predicted_probability, prediction_type, training_label, features, shap_contributions)
                   VALUES (%(model_version)s, %(species_id)s, %(predicted_probability)s, %(prediction_type)s, %(training_label)s, %(features)s, %(shap_contributions)s)""",
                rows,
            )

    report = {"model_version": version, "trained_at": trained_at.isoformat(), "training_data": training_data, "metrics": metrics,
              "highest_unlabelled": sorted(((r["species_id"], r["predicted_probability"]) for r in rows if r["prediction_type"] == "unlabelled"), key=lambda x: -x[1])[:10],
              "notes": ["Predictions are model output, not official IUCN assessments.",
                        "SHAP contributions describe model behaviour, not ecological causation.",
                        "Recording effort differs by taxonomic group; group indicators are included but bias remains."]}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("model_version", "training_data")}, indent=2))
    for name, scores in evaluation.items():
        print(f"{name:20} PR-AUC {scores['pr_auc']['mean']:.3f}±{scores['pr_auc']['sd']:.3f}  ROC-AUC {scores['roc_auc']['mean']:.3f}  "
              f"recall {scores['recall']['mean']:.2f}  precision {scores['precision']['mean']:.2f}  Brier {scores['brier']['mean']:.3f}")
    print("baseline PR-AUC (prevalence):", metrics["pr_auc_baseline_prevalence"], "| selected:", best_name)
    print("top features:", list(metrics["global_importance_mean_abs_shap"].items())[:6])
    print("highest predicted among unlabelled:", report["highest_unlabelled"][:8])


if __name__ == "__main__":
    main()
