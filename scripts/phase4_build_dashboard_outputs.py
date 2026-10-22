from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MASTER_FILE = ROOT / "extinct-species-since-1500" / "data" / "INDIA_BIODIVERSITY_MASTER_15K.xls"
STATE_BOUNDARIES_FILE = ROOT / "data" / "raw" / "india_states_admin_current.geojson"
PROTECTED_AREAS_FILE = ROOT / "data" / "raw" / "protected_areas" / "extracted" / "PA_TR_Corridor_Final.kml"
OUTPUT_DIR = ROOT / "data" / "processed"

YEAR_START = 2000
YEAR_END = 2025
YEARS = list(range(YEAR_START, YEAR_END + 1))
GRID_SIZE_DEG = 0.75
# State attribution shares the hotspot grid. This avoids repeatedly tracing the
# same detailed boundary for observations already represented by one map cell.
STATE_CACHE_SIZE_DEG = GRID_SIZE_DEG
HOTSPOT_LIMIT = 9

ALL_STATES = [
    "Andaman & Nicobar",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra & Nagar Haveli",
    "Daman & Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu & Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]

STATE_ALIASES = {
    "Andaman and Nicobar": "Andaman & Nicobar",
    "Dadar & Nagar Haveli": "Dadra & Nagar Haveli",
    "Dadra and Nagar Haveli": "Dadra & Nagar Haveli",
    "Jammu And Kashmir": "Jammu & Kashmir",
}

STATUS_RISK = {
    "CR": 0.95,
    "EN": 0.82,
    "VU": 0.64,
    "NT": 0.46,
    "LC": 0.28,
}

HUMAN_MODIFIED_HABITATS = {"Agricultural", "Urban"}


@dataclass(frozen=True)
class SpeciesMeta:
    species_id: str
    common_name: str
    scientific_name: str
    emoji: str
    status: str
    habitat: str
    taxonomic_group: str
    description: str


@dataclass
class RegionFeature:
    name: str
    polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]]
    bbox: tuple[float, float, float, float]
    centroid: tuple[float, float]


SPECIES_ORDER: list[SpeciesMeta] = [
    SpeciesMeta(
        species_id="tiger",
        common_name="Bengal Tiger",
        scientific_name="Panthera tigris",
        emoji="🐯",
        status="EN",
        habitat="Tropical forest, grassland, mangrove",
        taxonomic_group="Mammal",
        description="India's national animal and apex predator across forests, grasslands, and mangrove landscapes.",
    ),
    SpeciesMeta(
        species_id="elephant",
        common_name="Asian Elephant",
        scientific_name="Elephas maximus",
        emoji="🐘",
        status="EN",
        habitat="Tropical forest, grassland",
        taxonomic_group="Mammal",
        description="India supports the largest share of the world's wild Asian elephants, with corridor fragmentation a persistent pressure.",
    ),
    SpeciesMeta(
        species_id="rhino",
        common_name="Indian One-horned Rhinoceros",
        scientific_name="Rhinoceros unicornis",
        emoji="🦏",
        status="VU",
        habitat="Alluvial grassland, floodplain forest",
        taxonomic_group="Mammal",
        description="A recovery success story centered on alluvial floodplains, but still highly exposed to range concentration and flood dynamics.",
    ),
    SpeciesMeta(
        species_id="bear",
        common_name="Sloth Bear",
        scientific_name="Melursus ursinus",
        emoji="🐻",
        status="VU",
        habitat="Dry forest, scrubland, grassland",
        taxonomic_group="Mammal",
        description="A widespread Indian bear dependent on dry forest mosaics, facing persistent habitat loss and human conflict.",
    ),
    SpeciesMeta(
        species_id="croc",
        common_name="Mugger Crocodile",
        scientific_name="Crocodylus palustris",
        emoji="🐊",
        status="VU",
        habitat="Freshwater rivers, lakes, marshes",
        taxonomic_group="Reptile",
        description="A key freshwater predator whose records cluster along river, reservoir, and wetland systems under mounting land-use pressure.",
    ),
]

SPECIES_BY_SCIENTIFIC = {item.scientific_name: item for item in SPECIES_ORDER}


def normalize_state_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = " ".join(str(name).strip().split())
    return STATE_ALIASES.get(cleaned, cleaned)


def canonical_scientific_name(value: str) -> str:
    parts = str(value).strip().split()
    if len(parts) < 2:
        return str(value).strip()
    return f"{parts[0]} {parts[1]}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def point_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    eps: float = 1e-9,
) -> bool:
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -eps:
        return False
    length_sq = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= length_sq + eps


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    total = len(ring)
    if total < 3:
        return False

    for index in range(total):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % total]

        if point_on_segment(x, y, x1, y1, x2, y2):
            return True

        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside

    return inside


def point_in_polygon(
    x: float,
    y: float,
    polygon: tuple[list[tuple[float, float]], list[list[tuple[float, float]]]],
) -> bool:
    outer, holes = polygon
    if not point_in_ring(x, y, outer):
        return False
    for hole in holes:
        if point_in_ring(x, y, hole):
            return False
    return True


def flatten_points(rings: Iterable[Iterable[tuple[float, float]]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for ring in rings:
        points.extend(ring)
    return points


def bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def geometry_to_polygons(
    geometry: dict[str, object]
) -> list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]]:
    geom_type = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates")
    polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]] = []

    def convert_ring(raw_ring: list[list[float]]) -> list[tuple[float, float]]:
        return [(float(pair[0]), float(pair[1])) for pair in raw_ring if len(pair) >= 2]

    if geom_type == "Polygon" and isinstance(coordinates, list):
        if coordinates:
            outer = convert_ring(coordinates[0])
            holes = [convert_ring(raw) for raw in coordinates[1:]]
            polygons.append((outer, holes))
    elif geom_type == "MultiPolygon" and isinstance(coordinates, list):
        for raw_polygon in coordinates:
            if not raw_polygon:
                continue
            outer = convert_ring(raw_polygon[0])
            holes = [convert_ring(raw) for raw in raw_polygon[1:]]
            polygons.append((outer, holes))

    return polygons


def load_state_regions(path: Path) -> list[RegionFeature]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    regions: list[RegionFeature] = []

    for feature in features:
        properties = feature.get("properties") or {}
        raw_name = properties.get("state") or properties.get("NAME_1")
        name = normalize_state_name(str(raw_name)) if raw_name else None
        geometry = feature.get("geometry") or {}
        polygons = geometry_to_polygons(geometry)
        if not name or not polygons:
            continue

        points = flatten_points(
            [poly[0] for poly in polygons] + [hole for poly in polygons for hole in poly[1]]
        )
        bbox = bbox_from_points(points)
        centroid = ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)
        regions.append(RegionFeature(name=name, polygons=polygons, bbox=bbox, centroid=centroid))

    return regions


def load_pa_polygons(path: Path) -> list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]]:
    if not path.exists():
        return []

    tree = ET.parse(path)
    root = tree.getroot()
    polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]] = []

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    for polygon_el in root.iter():
        if local_name(polygon_el.tag) != "Polygon":
            continue

        outer_ring: list[tuple[float, float]] = []
        hole_rings: list[list[tuple[float, float]]] = []

        for child in polygon_el.iter():
            child_name = local_name(child.tag)
            if child_name != "coordinates" or not (child.text and child.text.strip()):
                continue
            raw_points = []
            for token in child.text.strip().split():
                pieces = token.split(",")
                if len(pieces) < 2:
                    continue
                raw_points.append((float(pieces[0]), float(pieces[1])))
            if not raw_points:
                continue
            if not outer_ring:
                outer_ring = raw_points
            else:
                hole_rings.append(raw_points)

        if outer_ring:
            polygons.append((outer_ring, hole_rings))

    return polygons


def bbox_contains(
    bbox: tuple[float, float, float, float],
    lon: float,
    lat: float,
    padding: float = 0.0,
) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        min_lon - padding <= lon <= max_lon + padding
        and min_lat - padding <= lat <= max_lat + padding
    )


def assign_state(lon: float, lat: float, regions: list[RegionFeature]) -> str | None:
    candidates = [region for region in regions if bbox_contains(region.bbox, lon, lat, padding=0.02)]

    for region in candidates:
        for polygon in region.polygons:
            if point_in_polygon(lon, lat, polygon):
                return region.name

    if candidates:
        nearest = min(candidates, key=lambda item: (item.centroid[0] - lon) ** 2 + (item.centroid[1] - lat) ** 2)
        return nearest.name

    nearest = min(regions, key=lambda item: (item.centroid[0] - lon) ** 2 + (item.centroid[1] - lat) ** 2)
    return nearest.name if 67.0 <= lon <= 99.5 and 5.0 <= lat <= 38.5 else None


def sample_cell_coverage(
    lon: float,
    lat: float,
    size_deg: float,
    pa_polygons: list[tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]],
) -> float | None:
    if not pa_polygons:
        return None

    sample_fracs = (0.2, 0.5, 0.8)
    samples = [
        (lon + size_deg * frac_x, lat + size_deg * frac_y)
        for frac_y in sample_fracs
        for frac_x in sample_fracs
    ]
    covered = 0

    for sample_lon, sample_lat in samples:
        if any(point_in_polygon(sample_lon, sample_lat, polygon) for polygon in pa_polygons):
            covered += 1

    return round(100.0 * covered / len(samples), 1)


def year_array(counter: Counter[int]) -> list[int]:
    raw = [int(counter.get(year, 0)) for year in YEARS]
    maximum = max(raw) if raw else 0
    if maximum <= 0:
        return [0 for _ in raw]
    return [int(round((value / maximum) * 100)) for value in raw]


def top_habitats(habitat_counter: Counter[str]) -> str:
    habitats = [name for name, _ in habitat_counter.most_common(3) if name]
    return ", ".join(habitats) if habitats else "Mixed recorded habitats"


def summarize_hotspot(feature_props: dict[str, object]) -> str:
    state_name = str(feature_props.get("dominant_state") or "a cross-state")
    richness = int(feature_props.get("species_richness") or 0)
    record_count = int(feature_props.get("record_count") or 0)
    pa_coverage = feature_props.get("pa_coverage_pct")

    summary = (
        f"{richness} tracked species and {record_count} occurrence records cluster around {state_name}."
    )
    if isinstance(pa_coverage, (int, float)):
        summary += f" Approximate protected-area overlap is {round(float(pa_coverage))}%."
    return summary


def main() -> None:
    if not MASTER_FILE.exists():
        raise FileNotFoundError(f"Master species export not found: {MASTER_FILE}")
    if not STATE_BOUNDARIES_FILE.exists():
        raise FileNotFoundError(f"State boundary GeoJSON not found: {STATE_BOUNDARIES_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    regions = load_state_regions(STATE_BOUNDARIES_FILE)
    region_names = {region.name for region in regions}
    missing_states = [state for state in ALL_STATES if state not in region_names]
    if missing_states:
        raise RuntimeError(f"Boundary dataset is missing expected states: {', '.join(missing_states)}")

    pa_polygons = load_pa_polygons(PROTECTED_AREAS_FILE)

    species_year_counts: dict[str, Counter[int]] = {meta.species_id: Counter() for meta in SPECIES_ORDER}
    species_habitats: dict[str, Counter[str]] = {meta.species_id: Counter() for meta in SPECIES_ORDER}
    species_state_counts: dict[str, Counter[str]] = {meta.species_id: Counter() for meta in SPECIES_ORDER}
    state_species_counts: dict[str, Counter[str]] = {state: Counter() for state in ALL_STATES}
    species_total_counts: Counter[str] = Counter()
    species_individual_totals: Counter[str] = Counter()
    species_human_modified: Counter[str] = Counter()
    species_bases: dict[str, Counter[str]] = {meta.species_id: Counter() for meta in SPECIES_ORDER}
    grid_cells: dict[tuple[float, float], dict[str, object]] = defaultdict(
        lambda: {
            "record_count": 0,
            "species_ids": set(),
            "states": Counter(),
        }
    )

    total_rows = 0
    assigned_rows = 0
    state_cache: dict[tuple[int, int], str | None] = {}

    with MASTER_FILE.open(encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total_rows += 1

            scientific_key = canonical_scientific_name(row.get("scientificName", ""))
            species_meta = SPECIES_BY_SCIENTIFIC.get(scientific_key)
            if species_meta is None:
                continue

            try:
                lat = float(row["decimalLatitude"])
                lon = float(row["decimalLongitude"])
                year = int(float(row["year"]))
            except (KeyError, TypeError, ValueError):
                continue

            state_cache_key = (
                math.floor(lat / STATE_CACHE_SIZE_DEG),
                math.floor(lon / STATE_CACHE_SIZE_DEG),
            )
            if state_cache_key not in state_cache:
                state_cache[state_cache_key] = assign_state(lon, lat, regions)
            state_name = state_cache[state_cache_key]
            if state_name:
                assigned_rows += 1

            habitat = str(row.get("habitat") or "").strip() or "Unknown habitat"
            basis = str(row.get("basisOfRecord") or "").strip() or "Unknown basis"
            individual_count = int(float(row.get("individualCount") or 0))

            species_total_counts[species_meta.species_id] += 1
            species_individual_totals[species_meta.species_id] += individual_count
            species_year_counts[species_meta.species_id][year] += 1
            species_habitats[species_meta.species_id][habitat] += 1
            species_bases[species_meta.species_id][basis] += 1

            if habitat in HUMAN_MODIFIED_HABITATS:
                species_human_modified[species_meta.species_id] += 1

            if state_name:
                species_state_counts[species_meta.species_id][state_name] += 1
                state_species_counts[state_name][species_meta.species_id] += 1

            lat_bin = round(math.floor(lat / GRID_SIZE_DEG) * GRID_SIZE_DEG, 2)
            lon_bin = round(math.floor(lon / GRID_SIZE_DEG) * GRID_SIZE_DEG, 2)
            cell = grid_cells[(lat_bin, lon_bin)]
            cell["record_count"] = int(cell["record_count"]) + 1
            cell["species_ids"].add(species_meta.species_id)
            if state_name:
                cell["states"][state_name] += 1

    species_metrics: dict[str, dict[str, object]] = {}

    for meta in SPECIES_ORDER:
        species_id = meta.species_id
        total = species_total_counts[species_id]
        trend = year_array(species_year_counts[species_id])
        early_avg = sum(trend[:6]) / 6 if trend else 0.0
        recent_avg = sum(trend[-6:]) / 6 if trend else 0.0
        trend_decline = clamp((early_avg - recent_avg) / 100.0, 0.0, 1.0)
        habitat_diversity = len(species_habitats[species_id])
        habitat_narrowness = clamp(1.0 - min(1.0, habitat_diversity / 5.0), 0.0, 1.0)
        state_coverage = clamp(len(species_state_counts[species_id]) / len(ALL_STATES), 0.0, 1.0)
        range_pressure = 1.0 - state_coverage
        human_pressure = (
            species_human_modified[species_id] / total if total else 0.0
        )
        status_risk = STATUS_RISK.get(meta.status.upper(), 0.5)

        worsening_prob = clamp(
            0.40 * status_risk
            + 0.20 * human_pressure
            + 0.15 * trend_decline
            + 0.15 * range_pressure
            + 0.10 * habitat_narrowness,
            0.0,
            0.98,
        )
        eri_score = round(
            100
            * (
                0.45 * status_risk
                + 0.20 * human_pressure
                + 0.15 * range_pressure
                + 0.10 * habitat_narrowness
                + 0.10 * trend_decline
            ),
            1,
        )
        priority_score = round((eri_score / 100.0 + worsening_prob) / 2.0, 3)

        drivers = [
            ("endangered conservation status", 0.40 * status_risk),
            ("high share of agricultural or urban habitat records", 0.20 * human_pressure),
            ("concentrated state footprint", 0.15 * range_pressure),
            ("weaker recent occurrence trend", 0.15 * trend_decline),
            ("narrow habitat diversity", 0.10 * habitat_narrowness),
        ]
        key_drivers = [label for label, score in sorted(drivers, key=lambda item: item[1], reverse=True) if score > 0.02][:3]

        species_metrics[species_id] = {
            "meta": meta,
            "trend": trend,
            "eri_score": eri_score,
            "worsening_prob": round(worsening_prob, 3),
            "priority_score": priority_score,
            "human_pressure": round(human_pressure, 3),
            "range_pressure": round(range_pressure, 3),
            "trend_decline": round(trend_decline, 3),
            "habitat_summary": top_habitats(species_habitats[species_id]),
            "key_drivers": key_drivers,
            "state_count": len(species_state_counts[species_id]),
        }

    state_species_payload: dict[str, list[dict[str, object]]] = {}
    for state in ALL_STATES:
        entries: list[dict[str, object]] = []
        for meta in SPECIES_ORDER:
            metrics = species_metrics[meta.species_id]
            obs = int(state_species_counts[state][meta.species_id])
            entries.append(
                {
                    "e": meta.emoji,
                    "n": meta.common_name,
                    "s": meta.scientific_name,
                    "st": meta.status.lower(),
                    "h": meta.habitat,
                    "obs": obs,
                    "trend": metrics["trend"],
                    "desc": meta.description,
                    "eri": metrics["eri_score"],
                    "taxonomic_group": meta.taxonomic_group,
                }
            )

        entries.sort(key=lambda item: (-int(item["obs"]), -int(item["eri"]), str(item["n"])))
        state_species_payload[state] = entries

    watchlist_payload: list[dict[str, object]] = []
    for meta in sorted(SPECIES_ORDER, key=lambda item: species_metrics[item.species_id]["priority_score"], reverse=True):
        metrics = species_metrics[meta.species_id]
        top_state = species_state_counts[meta.species_id].most_common(1)
        note_parts = metrics["key_drivers"][:2] or ["composite biodiversity pressure"]
        top_state_text = top_state[0][0] if top_state else "multiple states"
        watchlist_payload.append(
            {
                "species_id": meta.species_id,
                "common_name": meta.common_name,
                "scientific_name": meta.scientific_name,
                "taxonomic_group": meta.taxonomic_group,
                "iucn_category": meta.status,
                "emoji": meta.emoji,
                "eri_score": metrics["eri_score"],
                "predicted_worsening_prob": metrics["worsening_prob"],
                "priority_score": metrics["priority_score"],
                "key_drivers": metrics["key_drivers"],
                "note": (
                    f"Predicted risk escalation: {int(round(float(metrics['worsening_prob']) * 100))}% "
                    f"- strongest signals are {note_parts[0]} and {note_parts[1] if len(note_parts) > 1 else note_parts[0]}. "
                    f"Highest assigned observation load is in {top_state_text}."
                ),
            }
        )

    hotspot_rows: list[dict[str, object]] = []
    for (lat_bin, lon_bin), cell in grid_cells.items():
        record_count = int(cell["record_count"])
        species_ids = sorted(cell["species_ids"])
        if not record_count or not species_ids:
            continue

        average_risk = sum(float(species_metrics[species_id]["worsening_prob"]) for species_id in species_ids) / len(species_ids)
        hotspot_score = len(species_ids) * math.log1p(record_count) * (1.0 + average_risk)
        dominant_state = cell["states"].most_common(1)[0][0] if cell["states"] else "Cross-state"

        hotspot_rows.append(
            {
                "lat_bin": lat_bin,
                "lon_bin": lon_bin,
                "species_richness": len(species_ids),
                "record_count": record_count,
                "hotspot_score_raw": hotspot_score,
                "dominant_state": dominant_state,
                "species_ids": species_ids,
            }
        )

    hotspot_rows.sort(key=lambda item: item["hotspot_score_raw"], reverse=True)
    max_hotspot_score = hotspot_rows[0]["hotspot_score_raw"] if hotspot_rows else 1.0

    hotspot_features = []
    for rank, hotspot in enumerate(hotspot_rows[:HOTSPOT_LIMIT], start=1):
        score_norm = round(100.0 * float(hotspot["hotspot_score_raw"]) / max_hotspot_score, 1)
        pa_coverage = sample_cell_coverage(
            hotspot["lon_bin"],
            hotspot["lat_bin"],
            GRID_SIZE_DEG,
            pa_polygons,
        )

        if score_norm < 35:
            gap_status = "low_risk"
        elif pa_coverage is None:
            gap_status = "hotspot_unknown_pa"
        elif pa_coverage >= 40:
            gap_status = "protected_hotspot"
        else:
            gap_status = "gap_hotspot"

        region_name = f"{hotspot['dominant_state']} biodiversity cluster"
        props = {
            "rank": rank,
            "region_name": region_name,
            "dominant_state": hotspot["dominant_state"],
            "species_richness": hotspot["species_richness"],
            "record_count": hotspot["record_count"],
            "hotspot_score": score_norm,
            "hotspot_score_norm": score_norm,
            "pa_coverage_pct": pa_coverage,
            "gap_status": gap_status,
            "centroid_lat": round(float(hotspot["lat_bin"]) + GRID_SIZE_DEG / 2.0, 3),
            "centroid_lon": round(float(hotspot["lon_bin"]) + GRID_SIZE_DEG / 2.0, 3),
        }
        props["summary"] = summarize_hotspot(props)

        hotspot_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [hotspot["lon_bin"], hotspot["lat_bin"]],
                        [hotspot["lon_bin"] + GRID_SIZE_DEG, hotspot["lat_bin"]],
                        [hotspot["lon_bin"] + GRID_SIZE_DEG, hotspot["lat_bin"] + GRID_SIZE_DEG],
                        [hotspot["lon_bin"], hotspot["lat_bin"] + GRID_SIZE_DEG],
                        [hotspot["lon_bin"], hotspot["lat_bin"]],
                    ]],
                },
                "properties": props,
            }
        )

    state_species_path = OUTPUT_DIR / "state_species.json"
    hotspots_path = OUTPUT_DIR / "hotspots.geojson"
    watchlist_path = OUTPUT_DIR / "watchlist.json"

    state_species_path.write_text(
        json.dumps(state_species_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    hotspots_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": hotspot_features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    watchlist_path.write_text(
        json.dumps(watchlist_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {state_species_path}")
    print(f"Wrote {hotspots_path}")
    print(f"Wrote {watchlist_path}")
    print(f"  - Records processed: {total_rows}")
    print(f"  - Records assigned to states: {assigned_rows}")
    for meta in SPECIES_ORDER:
        metrics = species_metrics[meta.species_id]
        print(
            "  - "
            f"{meta.common_name}: {species_total_counts[meta.species_id]} records, "
            f"{metrics['state_count']} states, ERI {metrics['eri_score']}, "
            f"worsening {int(round(float(metrics['worsening_prob']) * 100))}%"
        )


if __name__ == "__main__":
    main()
