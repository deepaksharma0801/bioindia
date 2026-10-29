"""Export a static snapshot of the dashboard for GitHub Pages (no API or database needed to view it).

Writes site/ with the dashboard files, the three dashboard data files and the API answers the live
sections use (snapshot/v1/...), including every state report and the cascade scenarios offered in
the dashboard. Requires the loaded PostGIS database.

Public-release rule: Red List categories that come from the licensed IUCN export are not published
(the IUCN terms restrict redistribution). They appear as "-" and reports give only counts of
officially threatened species. The five flagship categories come from the project's own reference
list, are labelled unverified and are kept. Aggregate figures derived from GBIF records are published
with the GBIF download citation.

Usage: python scripts/export_static_site.py [--out site]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


FLAGSHIPS = ["tiger", "elephant", "rhino", "bear", "croc"]
CASCADE_SPECIES = FLAGSHIPS + ["ardeola_grayii", "pavo_cristatus"]  # the options in bioindia-phase5.js
CASCADE_THRESHOLDS = [0.25, 0.5, 0.75]
DASHBOARD_FILES = ["BioIndia_v3_Complete.html", "bioindia-phase2.js", "bioindia-phase3.js", "bioindia-phase5.js"]
DATA_FILES = ["state_species.json", "occurrence_points.json", "hotspots.geojson"]
WITHHELD = "-"
# Fields that carry a Red List category from the IUCN export.
IUCN_FIELDS = {"official_iucn_category", "official_category", "iucn_category", "reported_category", "current_iucn_status", "category",
               "official_iucn_status", "source_reported_iucn_status"}


def snapshot_key(path: str, body: dict | None = None) -> str:
    """Must match snapshotKey() in bioindia-phase5.js."""
    key = path.lstrip("/")
    if body:
        key += "__" + "_".join(f"{name}-{body[name]}" for name in sorted(body))
    return re.sub(r"[^A-Za-z0-9/._-]", "_", key) + ".json"


def scrub(value, species_id: str | None = None):
    """Blank IUCN-export categories everywhere except on the flagship species."""
    if isinstance(value, list):
        return [scrub(item, species_id) for item in value]
    if not isinstance(value, dict):
        return value
    owner = value.get("species_id", species_id)
    return {key: (None if key in IUCN_FIELDS and owner not in FLAGSHIPS and item is not None else scrub(item, owner))
            for key, item in value.items()}


def scrub_report(report: dict) -> dict:
    report = scrub(report)
    official = report["sections"]["threatened_species"][0]
    count = len(official["evidence"].get("species", []))
    report["sections"]["threatened_species"][0] = {
        "text": f"{count} species with records here are officially threatened (IUCN CR/EN/VU). Names and categories from the IUCN "
                "Red List export are not shown in this public snapshot.",
        "evidence": {"officially_threatened_species": count},
    }
    report.pop("markdown", None)
    return report


def write_dashboard(out: Path, stamp: str) -> None:
    """Copy the dashboard files into the site with the static-mode flag and the citation footer."""
    for name in DASHBOARD_FILES:
        shutil.copy2(ROOT / name, out / name)
    # Species photo index (Wikimedia Commons links and credits) from scripts/fetch_species_images.py.
    photos = ROOT / "data" / "processed" / "species_images.json"
    if photos.exists():
        (out / "data" / "processed").mkdir(parents=True, exist_ok=True)
        shutil.copy2(photos, out / "data" / "processed" / photos.name)
    html = (out / DASHBOARD_FILES[0]).read_text(encoding="utf-8")
    flag = (f'<script>window.BIOINDIA_STATIC = {{date: "{stamp}"}};</script>\n'
            '<style>.sp-st.s-\\-{opacity:.5}</style>\n</head>')
    note = ('<div style="position:relative;z-index:2;padding:14px 16px 18px;background:rgba(4,10,18,.92);'
            'font:11px/1.4 Georgia,serif;color:rgba(168,196,216,.75);text-align:center">Static snapshot of '
            f'{stamp}. GBIF.org occurrence download https://doi.org/10.15468/dl.dvgq2s; Hansen et al. Global Forest Change; GHSL; '
            'OpenStreetMap contributors (ODbL); species photos: Wikimedia Commons contributors, credited on each photo. IUCN Red List categories are not shown, except the five flagships '
            '(unverified reference list). Model outputs are not IUCN assessments.</div>\n</body>')
    html = html.replace("</head>", flag, 1).replace("</body>", note, 1)
    (out / DASHBOARD_FILES[0]).write_text(html, encoding="utf-8")
    (out / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><title>BioIndia</title>'
                                    f'<meta http-equiv="refresh" content="0; url={DASHBOARD_FILES[0]}">'
                                    f'<a href="{DASHBOARD_FILES[0]}">BioIndia dashboard</a>', encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    parser.add_argument("--assets-only", action="store_true", help="Only refresh the dashboard HTML/JS in an existing site, keeping its data and date.")
    args = parser.parse_args()
    out: Path = args.out
    if args.assets_only:
        stamp = re.search(r'BIOINDIA_STATIC = \{date: "([0-9-]+)"', (out / DASHBOARD_FILES[0]).read_text(encoding="utf-8"))
        write_dashboard(out, stamp.group(1) if stamp else date.today().isoformat())
        print(f"Refreshed dashboard files in {out}")
        return
    if out.exists():
        # Keep the publishing repository (site/.git) so the gh-pages history continues.
        for child in out.iterdir():
            if child.name != ".git":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    (out / "data" / "processed").mkdir(parents=True, exist_ok=True)
    client = TestClient(app)
    written = 0

    def save(path: str, payload, body: dict | None = None) -> None:
        nonlocal written
        target = out / "snapshot" / "v1" / snapshot_key(path, body)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        written += 1

    def get(path: str, species_id: str | None = None):
        response = client.get("/api/v1" + path)
        if response.status_code != 200:
            print(f"  skipped {path}: {response.status_code}")
            return None
        payload = scrub(response.json(), species_id)
        save(path, payload)
        return payload

    print("Model and explanations")
    get("/model-info")
    get("/model-performance")
    get("/prediction/ranking?limit=6&unlabelled_only=true")
    ranking = get("/prediction/ranking?limit=6")
    for species_id in {item["species_id"] for item in ranking["species"]} | set(FLAGSHIPS):
        get(f"/prediction/species/{species_id}/explanation", species_id)

    print("Flagship profiles")
    for species_id in FLAGSHIPS:
        for suffix in ("intelligence", "trend", "environment", "land-pressure"):
            get(f"/species/{species_id}/{suffix}", species_id)
        get(f"/prediction/species/{species_id}", species_id)

    print("Species intelligence profiles")
    species_list = get("/species")
    profiled = [item["species_id"] for item in species_list["species"] if item.get("observation_record_count")]
    for number, species_id in enumerate(profiled, start=1):
        for suffix in ("intelligence", "environment", "land-pressure"):
            get(f"/species/{species_id}/{suffix}", species_id)
        get(f"/prediction/species/{species_id}/explanation", species_id)
        get(f"/indices/ibvci/{species_id}", species_id)
        network = client.get(f"/api/v1/network/species/{species_id}")
        if network.status_code == 200:
            slim = {key: value for key, value in network.json().items() if key not in ("documented_interactions", "co_occurrence_associations")}
            save(f"/network/species/{species_id}", scrub(slim, species_id))
        if number % 25 == 0:
            print(f"  {number}/{len(profiled)} species", flush=True)

    print("Cascade scenarios")
    for species_id in CASCADE_SPECIES:
        for threshold in CASCADE_THRESHOLDS:
            body = {"species_id": species_id, "threshold": threshold}
            save("/simulation/extinction-cascade", scrub(client.post("/api/v1/simulation/extinction-cascade", json=body).json()), body)

    print("State reports")
    states = [item["state"] for item in client.get("/api/v1/land-use/states").json()["states"]]
    for state in states:
        response = client.post("/api/v1/reports/regional", json={"region": state})
        if response.status_code == 200:
            save("/reports/regional", scrub_report(response.json()), {"region": state})
        else:
            print(f"  no report for {state}: {response.status_code}")

    print("Dashboard data files")
    from app.services.species import state_profiles, species_occurrences
    from app.services.gis import hotspot_geojson
    profiles = state_profiles()
    for entries in profiles.values():
        for entry in entries:
            if entry.get("species_id") not in FLAGSHIPS:
                entry["st"] = WITHHELD
    for name, payload in (("state_species.json", profiles), ("occurrence_points.json", species_occurrences()), ("hotspots.geojson", hotspot_geojson())):
        (out / "data" / "processed" / name).write_text(json.dumps(payload, separators=(",", ":"), default=str), encoding="utf-8")

    write_dashboard(out, date.today().isoformat())
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"Wrote {written} API snapshots for {len(states)} states to {out} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
