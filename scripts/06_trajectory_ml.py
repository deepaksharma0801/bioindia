"""
SCRIPT 06 — Extinction Risk Trajectory Prediction (ML)
=======================================================
Prerequisites:
    pip install pandas numpy scikit-learn imbalanced-learn xgboost matplotlib seaborn

Inputs:
    data/species_master.csv
    data/iucn_assessments.csv     (from Script 02 — needs IUCN token)
    data/species_eri.json

Outputs:
    data/watchlist.json           (priority watchlist for dashboard)
    outputs/feature_importance.png
    outputs/confusion_matrix.png
    outputs/model_report.txt

Run: python 06_trajectory_ml.py
"""

import pandas as pd
import numpy as np
import json
import os
import warnings
warnings.filterwarnings("ignore")

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import (balanced_accuracy_score, f1_score,
                              classification_report, confusion_matrix)
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.impute import KNNImputer
import matplotlib.pyplot as plt
import seaborn as sns

try:
    from imblearn.over_sampling import SMOTE
    HAS_SMOTE = True
except ImportError:
    HAS_SMOTE = False
    print("imblearn not installed — using class_weight='balanced' instead of SMOTE")

os.makedirs("data", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ── Load data ────────────────────────────────────────────────
master_df = pd.read_csv("data/species_master.csv")
with open("data/species_eri.json") as f:
    eri_list = json.load(f)
eri_df = pd.DataFrame(eri_list)[["species_id","eri_score"]]
master_df = master_df.merge(eri_df, on="species_id", how="left")

ASSESS_FILE = "data/iucn_assessments.csv"
has_assess = os.path.exists(ASSESS_FILE)

if has_assess:
    assess_df = pd.read_csv(ASSESS_FILE)
    print(f"Assessment training data: {len(assess_df)} transition records")
    print(f"Label distribution:\n{assess_df['label'].value_counts().to_string()}")
else:
    print(f"⚠ {ASSESS_FILE} not found — running in PREDICTION-ONLY mode")
    print("  (No training data available; will produce a rule-based watchlist)")

# ── Feature columns ──────────────────────────────────────────
FEATURE_COLS = [
    "iucn_category_num",
    "population_trend_num",
    "threat_count",
    "gen_length_final",
    "log_eoo_inv",
    "habitat_risk",
    "eri_score",
]

def build_features(df):
    out = df.copy()
    out["log_eoo_inv"] = -np.log1p(out.get("eoo_km2_final", out.get("eoo_km2", 0)).fillna(0))
    out["habitat_risk"] = 1 / (out.get("habitat_count_final", out.get("habitat_count", 1)).replace(0, 0.5))
    if "threat_count_final" in out.columns:
        out["threat_count"] = out["threat_count_final"]
    else:
        out["threat_count"] = out.get("threat_count", 0)
    if "gen_length_final" not in out.columns:
        out["gen_length_final"] = out.get("generation_length_yrs", 10)
    return out[FEATURE_COLS]


# ── MODEL TRAINING (if assessment data available) ────────────
model = None
label_enc = LabelEncoder()

if has_assess and len(assess_df) >= 10:

    # Merge species traits onto assessment transitions
    assess_feat = assess_df.merge(
        master_df[["species_id", "iucn_category_num", "population_trend_num",
                   "eoo_km2_final", "threat_count_final", "gen_length_final",
                   "habitat_count_final", "eri_score"]].rename(columns={
                       "iucn_category_num": "iucn_category_num",
                   }),
        on="species_id", how="left"
    )
    # Override iucn_category_num with the PREVIOUS category (at time of feature capture)
    assess_feat["iucn_category_num"] = assess_feat["prev_category_num"]

    X = build_features(assess_feat)
    y_raw = assess_feat["label"].values
    y = label_enc.fit_transform(y_raw)

    print(f"\nTraining set: {len(X)} samples, {len(set(y_raw))} classes: {label_enc.classes_}")

    # Impute
    imputer = KNNImputer(n_neighbors=3)
    X_imp = imputer.fit_transform(X)

    # SMOTE or class_weight
    if HAS_SMOTE and len(X_imp) >= 20:
        try:
            sm = SMOTE(random_state=42)
            X_res, y_res = sm.fit_resample(X_imp, y)
            print(f"SMOTE applied: {len(X_res)} samples after resampling")
        except Exception as e:
            print(f"SMOTE failed ({e}) — using class_weight='balanced'")
            X_res, y_res = X_imp, y
            USE_CW = True
    else:
        X_res, y_res = X_imp, y

    # Train RandomForest
    rf = RandomForestClassifier(
        n_estimators=300, class_weight="balanced",
        max_depth=6, random_state=42, n_jobs=-1
    )
    rf.fit(X_res, y_res)
    model = rf
    model_imputer = imputer

    # Evaluate via CV
    cv = StratifiedKFold(n_splits=min(5, len(set(y))), shuffle=True, random_state=42)
    y_pred_cv = cross_val_predict(
        RandomForestClassifier(n_estimators=100, class_weight="balanced",
                               max_depth=6, random_state=42),
        X_imp, y, cv=cv
    )
    ba = balanced_accuracy_score(y, y_pred_cv)
    f1 = f1_score(y, y_pred_cv, average="macro")
    print(f"\nCross-validation results:")
    print(f"  Balanced Accuracy: {ba:.3f}")
    print(f"  Macro F1:          {f1:.3f}")
    print(f"\nClassification Report:")
    print(classification_report(y, y_pred_cv, target_names=label_enc.classes_))

    # Feature importance plot
    fi = pd.Series(rf.feature_importances_, index=FEATURE_COLS).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    fi.plot(kind="barh", ax=ax, color="steelblue")
    ax.set_title("Feature Importance — Extinction Risk Trajectory Model")
    ax.set_xlabel("Importance")
    plt.tight_layout()
    plt.savefig("outputs/feature_importance.png", dpi=150)
    plt.close()

    # Confusion matrix
    cm = confusion_matrix(y, y_pred_cv)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=label_enc.classes_, yticklabels=label_enc.classes_, ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion Matrix — Risk Trajectory Prediction")
    plt.tight_layout()
    plt.savefig("outputs/confusion_matrix.png", dpi=150)
    plt.close()

    # Save report
    with open("outputs/model_report.txt", "w") as f:
        f.write(f"Balanced Accuracy: {ba:.3f}\n")
        f.write(f"Macro F1:          {f1:.3f}\n\n")
        f.write(classification_report(y, y_pred_cv, target_names=label_enc.classes_))
    print("\n✅ Saved feature importance, confusion matrix, model report")


# ── PREDICT ON CURRENT SPECIES ────────────────────────────────
master_feat = build_features(master_df)

if model is not None:
    X_predict = model_imputer.transform(master_feat)
    proba = model.predict_proba(X_predict)

    # Class index for "worsened"
    worsen_idx = list(label_enc.classes_).index("worsened") if "worsened" in label_enc.classes_ else 0
    worsen_proba = proba[:, worsen_idx]

    master_df["worsening_prob"] = worsen_proba
else:
    # Rule-based proxy when no ML training data available
    # Higher ERI + higher IUCN category = higher predicted worsening probability
    cat_num = master_df["iucn_category_num"].fillna(3)
    eri_norm = master_df["eri_score"].fillna(50) / 100
    trend_num = master_df["population_trend_num"].fillna(0)
    master_df["worsening_prob"] = (
        0.4 * (cat_num / 7) +
        0.4 * eri_norm +
        0.2 * ((trend_num + 1) / 2)   # decreasing=1 -> contribution=1, increasing=-1 -> 0
    ).clip(0, 1)
    print("\n⚠ Using rule-based proxy for worsening probability (no ML training data)")


# ── Build Priority Watchlist ──────────────────────────────────
with open("data/species_eri.json") as f:
    eri_full = {r["species_id"]: r for r in json.load(f)}

watchlist_rows = master_df.copy()
watchlist_rows["eri_score"] = watchlist_rows["species_id"].map(
    lambda x: eri_full.get(x, {}).get("eri_score", 0)
)

# Priority = species in top quartile of BOTH ERI AND worsening_prob
eri_q75 = watchlist_rows["eri_score"].quantile(0.60)
wp_q75  = watchlist_rows["worsening_prob"].quantile(0.60)

priority = watchlist_rows[
    (watchlist_rows["eri_score"] >= eri_q75) &
    (watchlist_rows["worsening_prob"] >= wp_q75)
].copy()

priority["priority_score"] = (
    0.5 * priority["eri_score"] / 100 +
    0.5 * priority["worsening_prob"]
)
priority = priority.nlargest(20, "priority_score")

print(f"\n── Priority Watchlist ({len(priority)} species) ──")
print(priority[["common_name","iucn_category","eri_score","worsening_prob"]].to_string(index=False))

watchlist = []
for _, row in priority.iterrows():
    sp_id = row["species_id"]
    eri_entry = eri_full.get(sp_id, {})

    # Top 3 threat drivers (from feature importance or rule-based)
    drivers = []
    if row.get("population_trend_num", 0) == 1:
        drivers.append("declining population trend")
    if row.get("threat_count", 0) >= 4:
        drivers.append(f"{int(row.get('threat_count',0))} active threat categories")
    eoo = row.get("eoo_km2_final", row.get("eoo_km2", None))
    if eoo and eoo < 5000:
        drivers.append(f"restricted range ({int(eoo):,} km²)")
    if not drivers:
        drivers.append("high composite extinction risk")

    watchlist.append({
        "species_id": sp_id,
        "common_name": str(row.get("common_name", "")),
        "scientific_name": str(row.get("scientific_name", "")),
        "taxonomic_group": str(row.get("taxonomic_group", "")),
        "iucn_category": str(row.get("iucn_category", "")),
        "emoji": str(row.get("emoji", "")),
        "eri_score": round(float(row.get("eri_score", 0)), 1),
        "predicted_worsening_prob": round(float(row["worsening_prob"]), 3),
        "priority_score": round(float(row["priority_score"]), 3),
        "key_drivers": drivers[:3],
        "note": f"Predicted risk escalation: {int(row['worsening_prob']*100)}% — driven by {'; '.join(drivers[:2])}"
    })

with open("data/watchlist.json", "w") as f:
    json.dump(watchlist, f, indent=2)
print(f"\n✅ Saved watchlist.json ({len(watchlist)} priority species)")

print("\nAll analysis scripts complete.")
print("Outputs ready for dashboard integration:")
print("  data/state_species.json   → replaces STATE_DB in HTML")
print("  data/species_eri.json     → ERI badges in species section")
print("  data/hotspots.geojson     → replaces hardcoded hotspot grid")
print("  data/species_trends.json  → real trend arrays")
print("  data/watchlist.json       → priority watchlist section")
