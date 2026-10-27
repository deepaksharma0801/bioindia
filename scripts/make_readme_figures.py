"""Render the README figures (docs/figures/*.svg) from the loaded database and pipeline reports.

Plain SVG, no plotting library. Colours follow the dashboard (navy surface, teal data, gold reference
lines) and were checked for colour-vision separation and contrast on the navy surface.

Usage: python scripts/make_readme_figures.py
"""

from __future__ import annotations

import json
import math
import os
from html import escape
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
ANALYTICS = ROOT / "data" / "analytics"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

SURFACE = "#08111c"
PANEL_EDGE = "#16283a"
GRID = "#1a2b3c"
TEXT = "#ddeaf5"
TEXT_2 = "#a8c4d8"
TEXT_3 = "#6f8ca4"
ACCENT = "#3aa898"
REFERENCE = "#b08c33"
MUTED = "#3f586c"
RAMP = ["#1f5f5f", "#277a73", "#2f978a", "#4abaa8", "#8fdccd", "#d8f4ee"]
SERIF = "Georgia, 'Times New Roman', serif"
SANS = "'Segoe UI', Helvetica, Arial, sans-serif"


class Svg:
    def __init__(self, width: int, height: int, title: str, subtitle: str, source: str) -> None:
        self.width, self.height = width, height
        self.parts = [
            f'<rect width="{width}" height="{height}" rx="10" fill="{SURFACE}"/>',
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="none" stroke="{PANEL_EDGE}"/>',
            self.text(32, 44, title, size=21, family=SERIF, fill=TEXT),
            self.text(32, 68, subtitle, size=13, fill=TEXT_2),
            self.text(32, height - 18, source, size=11, fill=TEXT_3),
        ]

    @staticmethod
    def text(x: float, y: float, value: str, size: float = 12, fill: str = TEXT_2, anchor: str = "start",
             family: str = SANS, weight: str = "normal") -> str:
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" fill="{fill}" '
                f'text-anchor="{anchor}" font-weight="{weight}">{escape(value)}</text>')

    def add(self, *parts: str) -> None:
        self.parts.extend(parts)

    def save(self, name: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        body = "\n".join(self.parts)
        (OUT / name).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img">\n{body}\n</svg>\n', encoding="utf-8")
        print(f"  wrote docs/figures/{name}")


def hbar(x: float, y: float, length: float, thickness: float, fill: str, radius: float = 4) -> str:
    """Horizontal bar: square at the baseline (left), 4 px rounded data end (right)."""
    r = min(radius, length / 2, thickness / 2)
    if length <= 0:
        return ""
    return (f'<path d="M{x:.1f},{y:.1f} H{x + length - r:.1f} Q{x + length:.1f},{y:.1f} {x + length:.1f},{y + r:.1f} '
            f'V{y + thickness - r:.1f} Q{x + length:.1f},{y + thickness:.1f} {x + length - r:.1f},{y + thickness:.1f} '
            f'H{x:.1f} Z" fill="{fill}"/>')


def vbar(x: float, base: float, height: float, width: float, fill: str, radius: float = 4) -> str:
    """Vertical column: square at the baseline, rounded top."""
    r = min(radius, height / 2, width / 2)
    if height <= 0:
        return ""
    top = base - height
    return (f'<path d="M{x:.1f},{base:.1f} V{top + r:.1f} Q{x:.1f},{top:.1f} {x + r:.1f},{top:.1f} H{x + width - r:.1f} '
            f'Q{x + width:.1f},{top:.1f} {x + width:.1f},{top + r:.1f} V{base:.1f} Z" fill="{fill}"/>')


def compact(value: float) -> str:
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:.0f}"


# ---------------------------------------------------------------------------------------------------
def record_density_map(connection: psycopg.Connection) -> None:
    cells = connection.execute(
        "SELECT floor(longitude * 4)::int, floor(latitude * 4)::int, COUNT(*) FROM occurrences GROUP BY 1, 2").fetchall()
    states = connection.execute(
        "SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.03), 3) FROM reference_states").fetchall()
    total = connection.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]

    west, east, south, north = 67.5, 98.0, 6.0, 37.5
    scale_x = math.cos(math.radians(22))
    plot_w = 560
    plot_h = plot_w * (north - south) / ((east - west) * scale_x)
    left, top = 32, 92

    def project(lon: float, lat: float) -> tuple[float, float]:
        return left + (lon - west) / (east - west) * plot_w, top + (north - lat) / (north - south) * plot_h

    bins = [1, 10, 50, 200, 1000, 5000]
    svg = Svg(900, int(top + plot_h + 36), "Where biodiversity is recorded in India",
              f"{total:,} quality-controlled GBIF occurrence records for 173 species, counted on a 0.25° grid",
              "Source: GBIF.org (2026) doi:10.15468/dl.dvgq2s, screened and loaded by the BioIndia pipeline. "
              "Record density reflects where people observe, not species abundance.")
    cell_w = 0.25 / (east - west) * plot_w
    cell_h = 0.25 / (north - south) * plot_h
    for ix, iy, n in cells:
        step = max(i for i, edge in enumerate(bins) if n >= edge)
        x, y = project(ix / 4, (iy + 1) / 4)
        svg.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w:.2f}" height="{cell_h:.2f}" fill="{RAMP[step]}"/>')
    for (geojson,) in states:
        geometry = json.loads(geojson)
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            ring = polygon[0]
            if len(ring) < 4:
                continue
            path = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in (project(lon, lat) for lon, lat in ring)) + " Z"
            svg.add(f'<path d="{path}" fill="none" stroke="{TEXT_3}" stroke-opacity="0.55" stroke-width="0.6"/>')

    # Legend and key figures on the right.
    lx = 640
    svg.add(Svg.text(lx, 120, "Records per 0.25° cell", size=13, fill=TEXT))
    labels = ["1–9", "10–49", "50–199", "200–999", "1,000–4,999", "5,000 +"]
    for i, label in enumerate(labels):
        y = 140 + i * 26
        svg.add(f'<rect x="{lx}" y="{y}" width="18" height="18" rx="3" fill="{RAMP[i]}"/>',
                Svg.text(lx + 28, y + 14, label, size=12, fill=TEXT_2))
    busiest = sorted(cells, key=lambda c: -c[2])[:1][0]
    facts = [
        (f"{len(cells):,}", "grid cells with records"),
        (f"{busiest[2]:,}", f"records in the busiest cell ({busiest[1] / 4 + 0.125:.1f}°N, {busiest[0] / 4 + 0.125:.1f}°E)"),
        ("36", "states and union territories"),
    ]
    for i, (value, label) in enumerate(facts):
        y = 340 + i * 62
        svg.add(Svg.text(lx, y, value, size=26, fill=TEXT, family=SERIF), Svg.text(lx, y + 20, label, size=12, fill=TEXT_3))
    svg.save("record-density-map.svg")


# ---------------------------------------------------------------------------------------------------
SHORT_FEATURES = {
    "temperature_niche_breadth_c": "Temperature niche breadth",
    "group_fishes": "Taxonomic group: fishes",
    "forest_2000_share_occupied_cells": "Tree cover where recorded",
    "log_precipitation_niche_breadth_mm": "Precipitation niche breadth",
    "mean_elevation_m": "Mean elevation of records",
    "recent_forest_loss_share_occupied_cells": "Recent forest loss where recorded",
    "top_district_share": "Concentration in one district",
    "log_districts_occupied": "Districts occupied (range size)",
}


def model_performance() -> None:
    report = json.loads((ANALYTICS / "risk_model_report.json").read_text(encoding="utf-8"))
    metrics = report["metrics"]
    candidates = metrics["candidates"]
    selected = metrics["selected_model"]
    baseline = metrics["pr_auc_baseline_prevalence"]
    names = {"logistic_regression": "Logistic regression", "random_forest": "Random forest", "xgboost": "XGBoost"}
    training = report["training_data"]

    svg = Svg(900, 400, "Extinction-vulnerability model",
              f"Predicting IUCN threatened status (CR/EN/VU) for {training['labelled_species']} species "
              f"({training['threatened']} threatened); repeated stratified 5-fold cross-validation",
              "Model predictions are not IUCN assessments. SHAP values explain the model, not ecological causes.")

    # Left panel: PR-AUC with one-SD whiskers and the chance baseline.
    px, pw, ptop = 32, 380, 110
    svg.add(Svg.text(px, ptop, "Precision-recall AUC (mean ± 1 SD)", size=13, fill=TEXT))
    axis_left, axis_w = px + 140, pw - 160
    for tick in (0, 0.2, 0.4, 0.6):
        x = axis_left + tick / 0.7 * axis_w
        svg.add(f'<line x1="{x:.1f}" y1="{ptop + 18}" x2="{x:.1f}" y2="{ptop + 190}" stroke="{GRID}" stroke-width="1"/>',
                Svg.text(x, ptop + 208, f"{tick:.1f}", size=11, fill=TEXT_3, anchor="middle"))
    for i, key in enumerate(["logistic_regression", "random_forest", "xgboost"]):
        y = ptop + 36 + i * 52
        mean, sd = candidates[key]["pr_auc"]["mean"], candidates[key]["pr_auc"]["sd"]
        length = mean / 0.7 * axis_w
        colour = ACCENT if key == selected else MUTED
        svg.add(Svg.text(axis_left - 12, y + 16, names[key], size=12.5, fill=TEXT if key == selected else TEXT_2, anchor="end"),
                hbar(axis_left, y, length, 22, colour))
        lo, hi = axis_left + (mean - sd) / 0.7 * axis_w, axis_left + (mean + sd) / 0.7 * axis_w
        svg.add(f'<line x1="{lo:.1f}" y1="{y + 11}" x2="{hi:.1f}" y2="{y + 11}" stroke="{TEXT_2}" stroke-width="1.5"/>',
                f'<line x1="{lo:.1f}" y1="{y + 6}" x2="{lo:.1f}" y2="{y + 16}" stroke="{TEXT_2}" stroke-width="1.5"/>',
                f'<line x1="{hi:.1f}" y1="{y + 6}" x2="{hi:.1f}" y2="{y + 16}" stroke="{TEXT_2}" stroke-width="1.5"/>',
                Svg.text(hi + 8, y + 16, f"{mean:.2f}", size=12, fill=TEXT if key == selected else TEXT_2))
    bx = axis_left + baseline / 0.7 * axis_w
    svg.add(f'<line x1="{bx:.1f}" y1="{ptop + 24}" x2="{bx:.1f}" y2="{ptop + 190}" stroke="{REFERENCE}" stroke-width="2"/>',
            Svg.text(bx + 6, ptop + 186, f"chance {baseline:.2f}", size=11, fill=TEXT_2))
    svg.add(Svg.text(axis_left, ptop + 236, f"Selected: {names[selected]} · ROC-AUC {candidates[selected]['roc_auc']['mean']:.2f}",
                     size=12, fill=TEXT_2))

    # Right panel: global SHAP importance.
    rx, rtop = 470, 110
    svg.add(Svg.text(rx, rtop, "What drives the predictions (mean |SHAP|)", size=13, fill=TEXT))
    importance = sorted(metrics["global_importance_mean_abs_shap"].items(), key=lambda item: -item[1])[:7]
    top_value = importance[0][1]
    for i, (feature, value) in enumerate(importance):
        y = rtop + 24 + i * 30
        svg.add(Svg.text(rx, y + 13, SHORT_FEATURES.get(feature, feature.replace("_", " ")), size=12, fill=TEXT_2),
                hbar(rx + 215, y + 1, value / top_value * 150, 16, ACCENT if i == 0 else "#2f8a7d"),
                Svg.text(rx + 215 + value / top_value * 150 + 8, y + 13, f"{value:.3f}", size=11, fill=TEXT_3))
    svg.save("model-performance.svg")


# ---------------------------------------------------------------------------------------------------
def forest_loss(connection: psycopg.Connection) -> None:
    rows = connection.execute("""
        SELECT state, SUM(forest_2000_km2) AS forest,
               SUM((SELECT SUM(v) FROM unnest(forest_loss_km2_by_year[15:]) AS v)) AS recent
        FROM land_use_cells GROUP BY state HAVING SUM(forest_2000_km2) > 500
    """).fetchall()
    yearly = connection.execute("""
        SELECT ordinality, SUM(value) FROM land_use_cells, unnest(forest_loss_km2_by_year) WITH ORDINALITY AS t(value, ordinality)
        GROUP BY ordinality ORDER BY ordinality
    """).fetchall()
    totals = connection.execute("SELECT SUM(forest_2000_km2), SUM(forest_loss_km2) FROM land_use_cells").fetchone()

    svg = Svg(900, 470, "Tree-cover loss across India, 2001–2024",
              f"{totals[1]:,.0f} km² lost from {totals[0]:,.0f} km² of year-2000 tree cover (≥ 30% canopy), "
              "from 30 m Hansen Global Forest Change, aggregated to 5 km cells",
              "Source: Hansen et al. (2013) Global Forest Change v1.12, CC BY 4.0. Tree cover includes plantations; "
              "loss includes harvest and natural disturbance; regrowth is not subtracted.")

    # Left: states ranked by recent loss share.
    lx, ltop = 32, 108
    svg.add(Svg.text(lx, ltop, "Loss 2015–2024, % of 2000 tree cover (top 12 states)", size=13, fill=TEXT))
    top = sorted(rows, key=lambda r: -(r[2] / r[1]))[:12]
    max_share = max(r[2] / r[1] for r in top) * 100
    for i, (state, forest, recent) in enumerate(top):
        share = recent / forest * 100
        y = ltop + 20 + i * 24
        svg.add(Svg.text(lx + 150, y + 12, state, size=12, fill=TEXT_2, anchor="end"),
                hbar(lx + 160, y + 1, share / max_share * 200, 15, ACCENT if i < 3 else "#2f8a7d"),
                Svg.text(lx + 160 + share / max_share * 200 + 8, y + 12, f"{share:.1f}%", size=11.5, fill=TEXT_2))

    # Right: national yearly loss columns.
    rx, rtop, rw, rh = 480, 108, 380, 250
    svg.add(Svg.text(rx, rtop, "National tree-cover loss per year (km²)", size=13, fill=TEXT))
    values = [v for _, v in yearly]
    peak = max(values)
    ceiling = math.ceil(peak / 500) * 500
    base = rtop + 30 + rh - 40
    for tick in range(0, ceiling + 1, 500):
        y = base - tick / ceiling * (rh - 50)
        svg.add(f'<line x1="{rx + 40}" y1="{y:.1f}" x2="{rx + rw}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>',
                Svg.text(rx + 32, y + 4, f"{tick:,}", size=11, fill=TEXT_3, anchor="end"))
    slot = (rw - 50) / len(values)
    peak_year = 2000 + values.index(peak) + 1
    for i, value in enumerate(values):
        year = 2001 + i
        x = rx + 46 + i * slot
        svg.add(vbar(x, base, value / ceiling * (rh - 50), slot - 3, ACCENT if year == peak_year else "#2f8a7d"))
        if year in (2001, 2008, 2016, 2024):
            svg.add(Svg.text(x + (slot - 3) / 2, base + 16, str(year), size=11, fill=TEXT_3, anchor="middle"))
    px = rx + 46 + (peak_year - 2001) * slot + (slot - 3) / 2
    svg.add(Svg.text(px, base - peak / ceiling * (rh - 50) - 8, f"{peak_year}: {peak:,.0f} km²", size=11.5, fill=TEXT, anchor="end"))
    svg.save("forest-loss.svg")


# ---------------------------------------------------------------------------------------------------
def pipeline_funnel() -> None:
    screening = json.loads((ANALYTICS / "screening_report.json").read_text(encoding="utf-8"))
    load = json.loads((ANALYTICS / "load_report.json").read_text(encoding="utf-8"))
    raw = screening["input_records"]
    screened = raw - screening["excluded_at_record_level"]
    sampled = load["records_staged"]
    loaded = load["records_loaded"]
    stages = [
        ("GBIF download", raw, "4.7 million India records for 188 species"),
        ("Record-level screen", screened, f"−{raw - screened:,}: missing coordinates or dates, captive, fossil, flagged geography"),
        ("Per-species cap", sampled, f"−{screened - sampled:,}: reproducible sample capping the 14 most-recorded species at 72,000 records each"),
        ("Spatial rules", loaded, f"−{sampled - loaded:,}: duplicate uploads, zoo locations, points outside India"),
    ]
    svg = Svg(900, 350, "From raw download to analysis-ready data",
              "Every exclusion is logged with its reason; coordinate uncertainty is kept as a quality class on every record",
              "Source: data/analytics/screening_report.json and load_report.json. Sampling uses a SHA-256 hash of a fixed seed and the GBIF ID.")
    left, width, top = 210, 640, 100
    for i, (label, value, note) in enumerate(stages):
        y = top + i * 52
        length = value / raw * width
        svg.add(Svg.text(left - 14, y + 17, label, size=13, fill=TEXT, anchor="end"),
                hbar(left, y, length, 24, ACCENT if i == len(stages) - 1 else "#2f8a7d" if i else MUTED),
                Svg.text(left + length + 10 if length < width - 120 else left + length - 10, y + 17, compact(value) if i else f"{value:,}",
                         size=12.5, fill=TEXT, anchor="start" if length < width - 120 else "end"),
                Svg.text(left, y + 42, note, size=11.5, fill=TEXT_3))
    svg.save("pipeline-funnel.svg")


def main() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        record_density_map(connection)
        forest_loss(connection)
    model_performance()
    pipeline_funnel()


if __name__ == "__main__":
    main()
