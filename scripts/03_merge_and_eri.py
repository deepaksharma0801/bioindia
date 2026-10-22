"""
SCRIPT 03 — Merge Data & Compute Extinction Risk Index (ERI)
=============================================================
Prerequisites:
    pip install pandas numpy scikit-learn scipy matplotlib seaborn

Inputs:
    data/species_list.csv
    data/iucn_traits.csv
    data/occurrences_by_state.csv

Output:
    data/species_master.csv     (merged, with imputed values)
    data/species_eri.json       (ERI scores for dashboard)
    outputs/pca_biplot.png      (Figure for research paper)
    outputs/eri_by_group.png    (ERI distribution by taxonomic group)

Run: python 03_merge_and_eri.py
"""

import pandas as pd
import numpy as np
import json
import os
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.impute import KNNImputer
from scipy import stats

os.makedirs("data", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# ── Load data ────────────────────────────────────────────────
species_df  = pd.read_csv("data/species_list.csv")
iucn_df     = pd.read_csv("data/iucn_traits.csv")
state_df    = pd.read_csv("data/occurrences_by_state.csv")

print(f"Species list: {len(species_df)} rows")
print(f"IUCN traits:  {len(iucn_df)} rows")


# ── Merge ────────────────────────────────────────────────────
df = species_df.merge(
    iucn_df[["species_id", "threat_count_iucn", "habitat_count_iucn",
             "eoo_km2_iucn", "aoo_km2_iucn", "generation_length_yrs_iucn"]],
    on="species_id", how="left"
)

# Prefer IUCN values; fall back to species_list values
df["threat_count_final"] = df["threat_count_iucn"].fillna(df["threat_count"])
df["habitat_count_final"] = df["habitat_count_iucn"].fillna(df["habitat_count"])
df["eoo_km2_final"] = df["eoo_km2_iucn"].fillna(df["eoo_km2"])
df["aoo_km2_final"] = df["aoo_km2_iucn"].fillna(df["aoo_km2"])
df["gen_length_final"] = df["generation_length_yrs_iucn"].fillna(df["generation_length_yrs"])

# Total GBIF observations per species (across all states)
if not state_df.empty:
    total_obs = state_df.groupby("species_id")["obs_count"].sum().reset_index()
    total_obs.columns = ["species_id", "total_gbif_obs"]
    df = df.merge(total_obs, on="species_id", how="left")
else:
    df["total_gbif_obs"] = 0

df.to_csv("data/species_master.csv", index=False)
print(f"✅ Saved merged data to data/species_master.csv")


# ── Feature Matrix for PCA / ERI ────────────────────────────
# Variables:
#   1. iucn_category_num (LC=2 ... EX=7)
#   2. population_trend_num (decreasing=1, stable=0, increasing=-1)
#   3. log_eoo_km2 (log of range size — smaller range = higher risk)
#   4. threat_count_final (more threats = higher risk)
#   5. gen_length_final (longer = slower recovery = higher vulnerability)
#   6. habitat_count_final (fewer habitats = more specialist = higher risk)
#      (inverted so that low habitat count → high risk)

feature_cols = [
    "iucn_category_num",
    "population_trend_num",
    "threat_count_final",
    "gen_length_final",
]

df_eri = df.copy()

# Log-transform range size (handle zeros)
df_eri["log_eoo"] = np.log1p(df_eri["eoo_km2_final"])
df_eri["log_eoo_inv"] = -df_eri["log_eoo"]    # invert: small range = high risk

# Invert habitat count: fewer habitats = higher risk
df_eri["habitat_risk"] = 1 / (df_eri["habitat_count_final"].replace(0, 0.5))

feature_cols_full = [
    "iucn_category_num",
    "population_trend_num",
    "threat_count_final",
    "gen_length_final",
    "log_eoo_inv",
    "habitat_risk",
]

X = df_eri[feature_cols_full].copy()
print(f"\nFeature matrix shape: {X.shape}")
print(f"Missing values:\n{X.isnull().sum()}")


# ── Imputation (KNN — better than mean for ecological data) ──
imputer = KNNImputer(n_neighbors=3)
X_imputed = pd.DataFrame(
    imputer.fit_transform(X),
    columns=feature_cols_full
)
print(f"\nAfter imputation, missing values: {X_imputed.isnull().sum().sum()}")


# ── Standardize ──────────────────────────────────────────────
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X_imputed)


# ── PCA ──────────────────────────────────────────────────────
pca = PCA(n_components=len(feature_cols_full))
pca.fit(X_scaled)

print(f"\nPCA Explained Variance Ratios:")
for i, ev in enumerate(pca.explained_variance_ratio_):
    print(f"  PC{i+1}: {ev:.3f} ({ev*100:.1f}%)")

print(f"\nPC1 Loadings (Extinction Risk axis):")
loadings = pd.Series(pca.components_[0], index=feature_cols_full)
print(loadings.sort_values(ascending=False).to_string())


# ── ERI Construction ─────────────────────────────────────────
# PC1 scores capture the primary risk axis
# If PC1 has positive loadings on risk variables, use PC1 scores directly.
# If flipped (negative loadings on risk = high risk), invert the sign.
pc1_scores = pca.transform(X_scaled)[:, 0]
pc2_scores = pca.transform(X_scaled)[:, 1]

# Check if PC1 is oriented correctly (higher score = higher risk)
# iucn_category_num should load positively on PC1 for risk axis
if pca.components_[0][feature_cols_full.index("iucn_category_num")] < 0:
    print("\n↩ Inverting PC1 sign (currently: high score = low risk)")
    pc1_scores = -pc1_scores

# Normalize to 0-100
eri_min, eri_max = pc1_scores.min(), pc1_scores.max()
eri_scores = 100 * (pc1_scores - eri_min) / (eri_max - eri_min)

df_eri["eri_score"] = eri_scores.round(1)
df_eri["eri_rank"] = df_eri["eri_score"].rank(ascending=False, method="min").astype(int)

print(f"\n── Top 15 Species by ERI ──")
top = df_eri.nlargest(15, "eri_score")[
    ["eri_rank", "common_name", "taxonomic_group", "iucn_category", "eri_score"]
]
print(top.to_string(index=False))


# ── Validation: ERI vs IUCN category ────────────────────────
# Should correlate but not be identical
corr, pval = stats.spearmanr(
    df_eri["iucn_category_num"].fillna(0),
    df_eri["eri_score"]
)
print(f"\nSpearman correlation (ERI vs IUCN category): r={corr:.3f}, p={pval:.4f}")


# ── Save species_eri.json for dashboard ─────────────────────
eri_output = df_eri[[
    "species_id", "common_name", "scientific_name",
    "taxonomic_group", "iucn_category", "iucn_status_code",
    "eri_score", "eri_rank", "emoji",
    "population_trend", "threat_count_final"
]].rename(columns={
    "threat_count_final": "threat_count",
}).copy()

eri_output["eri_score"] = eri_output["eri_score"].round(1)

eri_list = eri_output.where(pd.notnull(eri_output), None).to_dict(orient="records")
with open("data/species_eri.json", "w") as f:
    json.dump(eri_list, f, indent=2)
print(f"\n✅ Saved ERI scores to data/species_eri.json")


# ── Figure 1: PCA Biplot ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 8))
scatter = ax.scatter(
    pca.transform(X_scaled)[:, 0],
    pca.transform(X_scaled)[:, 1],
    c=df_eri["iucn_category_num"],
    cmap="RdYlGn_r", s=80, alpha=0.8, edgecolors="k", linewidths=0.5
)
plt.colorbar(scatter, ax=ax, label="IUCN Category (2=LC ... 7=EX)")

# Arrows for loadings
scale = 3
for i, feat in enumerate(feature_cols_full):
    ax.annotate(
        "", xy=(pca.components_[0][i]*scale, pca.components_[1][i]*scale),
        xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="darkblue", lw=1.5)
    )
    ax.text(
        pca.components_[0][i]*scale*1.1, pca.components_[1][i]*scale*1.1,
        feat.replace("_", " "), fontsize=8, color="darkblue"
    )

ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]*100:.1f}% variance)")
ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]*100:.1f}% variance)")
ax.set_title("PCA Biplot — Indian Threatened Species Extinction Risk Variables")
ax.axhline(0, color="grey", lw=0.5, ls="--")
ax.axvline(0, color="grey", lw=0.5, ls="--")
plt.tight_layout()
plt.savefig("outputs/pca_biplot.png", dpi=150)
plt.close()
print("✅ Saved PCA biplot to outputs/pca_biplot.png")


# ── Figure 2: ERI Distribution by Taxonomic Group ───────────
fig, ax = plt.subplots(figsize=(10, 5))
order = df_eri.groupby("taxonomic_group")["eri_score"].median().sort_values(ascending=False).index
sns.boxplot(data=df_eri, x="taxonomic_group", y="eri_score",
            order=order, palette="Reds_r", ax=ax)
ax.set_title("Extinction Risk Index (ERI) by Taxonomic Group — India")
ax.set_xlabel("Taxonomic Group")
ax.set_ylabel("ERI Score (0–100)")
plt.xticks(rotation=30)
plt.tight_layout()
plt.savefig("outputs/eri_by_group.png", dpi=150)
plt.close()
print("✅ Saved ERI distribution plot to outputs/eri_by_group.png")

print("\nDone. Next: run 04_trends.py")
