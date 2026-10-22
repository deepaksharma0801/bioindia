"""Extract OSM protected-area polygons for India and compare their coverage with the WDPA wildlife layer.

Inputs:
    data/raw/protected_areas/osm/india-latest.osm.pbf   (Geofabrik extract, ODbL)
    data/processed/wdpa_wildlife_protected_areas.gpkg   (from phase11_load_wdpa.py)

Outputs:
    data/processed/osm_protected_areas.gpkg
    data/analytics/osm_wdpa_protected_area_comparison.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely import make_valid
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data" / "raw" / "protected_areas" / "osm" / "india-latest.osm.pbf"
COUNTRIES = ROOT / "data" / "raw" / "boundaries" / "ne_10m_admin_0_countries.zip"
NEIGHBOURS = ("PAK", "CHN", "NPL", "BTN", "BGD", "MMR", "LKA")
# Indian sanctuaries on the border that Natural Earth's coarse 1:10m boundary places partly in a neighbour.
INDIAN_BORDER_SITES = ("Pangolakha WLS", "Yangoupokpi Lokchao WLS")
WDPA_WILDLIFE = ROOT / "data" / "processed" / "wdpa_wildlife_protected_areas.gpkg"
RAW_EXTRACT = ROOT / "data" / "raw" / "protected_areas" / "osm" / "osm_protected_raw_extract.gpkg"
OUTPUT = ROOT / "data" / "processed" / "osm_protected_areas.gpkg"
REPORT = ROOT / "data" / "analytics" / "osm_wdpa_protected_area_comparison.json"
EQUAL_AREA_CRS = "EPSG:6933"

CORE_CLASSES = ("national_park", "wildlife_sanctuary", "conservation_community_reserve")
REFERENCE_SITES = [
    "Kaziranga", "Corbett", "Kanha", "Periyar", "Sunderban", "Bandipur", "Ranthambhore", "Nagarhole",
    "Manas", "Gir", "Pench", "Tadoba", "Bandhavgarh", "Dudhwa", "Simlipal", "Silent Valley",
]
EXCLUDE_PATTERN = re.compile(r"\besz\b|eco[- ]?sensitive|\(proposed\)|buffer|corridor|zone of influence", re.IGNORECASE)
OTHER_TAG_PATTERN = re.compile(r'"([^"]+)"=>"((?:[^"\\]|\\.)*)"')
PROTECTED_FILTER = "boundary IN ('national_park', 'protected_area') OR leisure = 'nature_reserve'"


def parse_other_tags(value: str | None) -> dict[str, str]:
    return dict(OTHER_TAG_PATTERN.findall(value or ""))


def classify(tags: dict[str, str]) -> str:
    text = " ".join(tags.get(key) or "" for key in ("name", "name:en", "protection_title", "designation")).casefold()
    if EXCLUDE_PATTERN.search(text):
        return "excluded_zone_or_proposed"
    if "tiger reserve" in text:
        return "tiger_reserve"
    if "national park" in text or "nationalpark" in text or tags.get("boundary") == "national_park":
        return "national_park"
    if "sanctuary" in text or re.search(r"\bw\.?l\.?s\b", text) or "wildlife reserve" in text:
        return "wildlife_sanctuary"
    if "conservation reserve" in text or "community reserve" in text:
        return "conservation_community_reserve"
    if re.search(r"reserved? forest|protected forest|\brf\b", text):
        return "forest"
    return "other"


DUAL_PA_NAME_PATTERN = re.compile(r"national ?park|sanctuary|\bw\.?l\.?s\b", re.IGNORECASE)
# Tiger reserves whose OSM name does not say National Park or WLS, but whose core is one and has
# no separate OSM outline. Each entry is a documented project decision (decided 2026-10-22).
MANUAL_DUAL_SITES = {
    "Anamalai Tiger Reserve": "Core area is Indira Gandhi Wildlife Sanctuary and National Park, which OSM does not map separately.",
}


def dual_basis(tags: dict[str, str]) -> str | None:
    """Why a tiger reserve also counts as a wildlife protected area, or None if it does not.

    OSM often maps a park or sanctuary and its tiger reserve as one feature (e.g.
    'Sathyamangalam WLS/Tiger Reserve'), so such features count in both layers. The outline
    may include buffer zones.
    """
    if classify(tags) != "tiger_reserve":
        return None
    name = " ".join(tags.get(key) or "" for key in ("name", "name:en"))
    if DUAL_PA_NAME_PATTERN.search(name):
        return "name says National Park or WLS/Sanctuary"
    for site, reason in MANUAL_DUAL_SITES.items():
        if site in (tags.get("name"), tags.get("name:en")):
            return f"manual list: {reason}"
    return None


def also_wildlife_pa(tags: dict[str, str]) -> bool:
    return dual_basis(tags) is not None


def text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def read_protected_features() -> gpd.GeoDataFrame:
    """Read protected-area features from the PBF once; later runs reuse the cached extract."""
    if RAW_EXTRACT.exists() and RAW_EXTRACT.stat().st_mtime >= PBF.stat().st_mtime:
        return gpd.read_file(RAW_EXTRACT)
    frame = pyogrio.read_dataframe(
        PBF,
        layer="multipolygons",
        columns=["osm_id", "osm_way_id", "name", "boundary", "leisure", "other_tags"],
        where=PROTECTED_FILTER,
    )
    RAW_EXTRACT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(RAW_EXTRACT, driver="GPKG", layer="osm_protected_raw")
    return frame


def build_osm() -> gpd.GeoDataFrame:
    frame = read_protected_features()
    records = []
    for row in frame.itertuples(index=False):
        name = text_or_none(row.name)
        tags = {
            **parse_other_tags(text_or_none(row.other_tags)),
            "name": name,
            "boundary": text_or_none(row.boundary),
            "leisure": text_or_none(row.leisure),
        }
        records.append({
            "osm_id": f"relation/{row.osm_id}" if text_or_none(row.osm_id) else f"way/{row.osm_way_id}",
            "name": tags.get("name:en") or name,
            "osm_class": classify(tags),
            "also_wildlife_pa": also_wildlife_pa(tags),
            "dual_basis": dual_basis(tags),
            "protection_title": tags.get("protection_title"),
            "protect_class": tags.get("protect_class"),
            "wikidata": tags.get("wikidata"),
            "geometry": make_valid(row.geometry) if row.geometry is not None else None,
        })
    osm = gpd.GeoDataFrame(records, crs=frame.crs).dropna(subset=["geometry"])
    return osm[osm.geometry.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]


def drop_foreign_features(osm: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, list[str]]:
    """The Geofabrik extract extends past the border; drop features whose interior point is on a neighbour's land.

    A land-only India boundary would wrongly drop offshore marine parks and island sanctuaries
    whose interior point lies in the sea, so the test excludes neighbour land instead of
    requiring India land. Geometries are kept whole, not clipped.
    """
    projected = osm.to_crs(EQUAL_AREA_CRS)
    countries = gpd.read_file(f"zip://{COUNTRIES}").to_crs(EQUAL_AREA_CRS)
    neighbour_land = make_valid(unary_union(countries[countries["ADM0_A3"].isin(NEIGHBOURS)].geometry.values))
    share_on_neighbour_land = projected.geometry.intersection(neighbour_land).area / projected.geometry.area
    foreign = projected.geometry.representative_point().within(neighbour_land) | (share_on_neighbour_land >= 0.5)
    foreign &= ~osm["name"].isin(INDIAN_BORDER_SITES)
    return osm[~foreign], sorted(osm.loc[foreign, "name"].fillna("(unnamed)"))


def area_km2(frame: gpd.GeoDataFrame) -> float:
    if frame.empty:
        return 0.0
    return round(float(unary_union(frame.to_crs(EQUAL_AREA_CRS).geometry.values).area) / 1e6, 1)


def main() -> None:
    osm, foreign_dropped = drop_foreign_features(build_osm())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    osm.to_file(OUTPUT, driver="GPKG", layer="osm_protected_areas")

    wdpa = gpd.read_file(WDPA_WILDLIFE)
    core = osm[osm["osm_class"].isin(CORE_CLASSES) | osm["also_wildlife_pa"]]
    osm_core_union = unary_union(core.to_crs(EQUAL_AREA_CRS).geometry.values)
    dual = osm[osm["also_wildlife_pa"]].to_crs(EQUAL_AREA_CRS)
    wdpa_union = unary_union(wdpa.to_crs(EQUAL_AREA_CRS).geometry.values)
    overlap_km2 = osm_core_union.intersection(wdpa_union).area / 1e6
    wdpa_km2 = wdpa_union.area / 1e6

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "osm_source": "OpenStreetMap contributors, Geofabrik india-latest.osm.pbf (ODbL 1.0)",
        "osm_features": int(len(osm)),
        "foreign_features_dropped": foreign_dropped,
        "foreign_filter": "dropped when the feature interior point, or at least 50% of its area, lies on Natural Earth land of Pakistan, China, Nepal, Bhutan, Bangladesh, Myanmar or Sri Lanka, except listed Indian border sanctuaries; geometries not clipped",
        "osm_by_class": {
            osm_class: {"features": int(len(group)), "dissolved_area_km2": area_km2(group)}
            for osm_class, group in osm.groupby("osm_class")
        },
        "tiger_reserves_also_counted_as_wildlife_pa": [
            {"osm_id": record.osm_id, "name": record.name, "area_km2": round(record.geometry.area / 1e6, 1), "basis": record.dual_basis}
            for record in dual.sort_values("name").itertuples(index=False)
        ],
        "dual_classification_rule": "tiger_reserve features whose name also says National Park or WLS/Sanctuary, or that are on the documented manual list, are counted in both layers; their outline may include buffer zones",
        "manual_dual_sites": MANUAL_DUAL_SITES,
        "osm_core_wildlife_area_km2": round(osm_core_union.area / 1e6, 1),
        "wdpa_wildlife_layer_features": int(len(wdpa)),
        "wdpa_wildlife_area_km2": round(wdpa_km2, 1),
        "overlap_km2": round(overlap_km2, 1),
        "share_of_wdpa_wildlife_area_also_in_osm_core_percent": round(100 * overlap_km2 / wdpa_km2, 1) if wdpa_km2 else None,
        "reference_sites": {
            site: {
                "osm": sorted({f"{name} [{osm_class}]" for name, osm_class in zip(osm["name"], osm["osm_class"]) if isinstance(name, str) and site.casefold() in name.casefold()}),
                "wdpa_wildlife_layer": sorted({name for name in wdpa["NAME_ENG"].dropna() if site.casefold() in name.casefold()}),
            }
            for site in REFERENCE_SITES
        },
        "classification_note": "OSM classes come from name, protection_title and designation tags. ESZs, buffers, corridors and proposed sites are excluded. Tiger reserves include buffer zones and are reported separately from the core wildlife layer, except dual-named features listed in tiger_reserves_also_counted_as_wildlife_pa.",
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "reference_sites"}, indent=2, ensure_ascii=False))
    for site, found in report["reference_sites"].items():
        print(f"{site:13} OSM={found['osm'][:2]}  WDPA={found['wdpa_wildlife_layer'][:2]}")


if __name__ == "__main__":
    main()
