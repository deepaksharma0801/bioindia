"""Phase 20: automated regional (state) reports built only from database queries.

Every statement is produced by a fixed template from structured results and carries the numbers
it uses in `evidence`, so each figure can be traced. No language model writes any text.
District-level reports are not offered: occurrences are attributed to states only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .db import fetch_all
from .indices import cipi
from .land_pressure import state_land_use


class ReportError(ValueError):
    """Unknown region."""


def _statement(text: str, **evidence: Any) -> dict[str, Any]:
    return {"text": text, "evidence": evidence}


def _pressure_statements(state: str) -> list[dict[str, Any]]:
    land = state_land_use(state)
    if land is None:
        return [_statement("Land-use and forest-change data are not available for this state, so environmental pressures are not reported.", available=False)]
    states = state_land_use()["states"]
    recent_rank = 1 + sum(1 for other in states if (other["recent_forest_loss_2015_2024_pct"] or 0) > (land["recent_forest_loss_2015_2024_pct"] or 0))
    yearly = land["forest_loss_km2_by_year"]
    peak_year = max(yearly, key=yearly.get)
    statements = [
        _statement(f"Tree cover of at least 30% canopy covered {land['forest_2000_km2']:,} km2 ({land['forest_2000_pct_of_land']}% of land) in 2000 "
                   f"(Hansen Global Forest Change; includes plantations).",
                   forest_2000_km2=land["forest_2000_km2"], forest_2000_pct_of_land=land["forest_2000_pct_of_land"]),
        _statement(f"{land['forest_loss_2001_2024_km2']:,} km2 of that tree cover was lost in 2001-2024 ({land['forest_loss_pct_of_2000_forest']}% of the 2000 extent; "
                   f"{land['recent_forest_loss_2015_2024_pct']}% in 2015-2024, rank {recent_rank} of {len(states)} states). The largest annual loss was in {peak_year} "
                   f"({yearly[peak_year]:,} km2). Loss includes plantation harvest and natural disturbance; regrowth is not subtracted.",
                   forest_loss_km2=land["forest_loss_2001_2024_km2"], loss_pct=land["forest_loss_pct_of_2000_forest"],
                   recent_loss_pct=land["recent_forest_loss_2015_2024_pct"], recent_loss_rank=recent_rank, states_compared=len(states),
                   peak_year=int(peak_year), peak_year_km2=yearly[peak_year]),
        _statement(f"Built-up surfaces cover {land['built_up_pct_of_land']}% of land and population density is {land['population_density_per_km2']:,} people per km2 (GHSL 2020).",
                   built_up_pct=land["built_up_pct_of_land"], population_density_per_km2=land["population_density_per_km2"]),
    ]
    if land["forest_edge_share"] is not None:
        statements.append(_statement(f"{100 * land['forest_edge_share']:.0f}% of 30 m tree-cover pixels lie on a forest edge (a fragmentation indicator; higher means more fragmented).",
                                     forest_edge_share=land["forest_edge_share"]))
    statements.append(_statement("These describe pressures on places; they do not show effects on any species.", note=True))
    return statements


def regional_report(state: str) -> dict[str, Any]:
    overview = fetch_all(
        """SELECT COUNT(*)::integer AS records, COUNT(DISTINCT species_id)::integer AS species,
                  MIN(year)::integer AS first_year, MAX(year)::integer AS last_year,
                  COUNT(*) FILTER (WHERE coordinate_uncertainty_class IN ('precise', 'moderate'))::integer AS precise_records
           FROM occurrences WHERE state = %(state)s""",
        {"state": state},
    )[0]
    if not overview["records"]:
        raise ReportError(f"No occurrence records for region '{state}'.")

    species = fetch_all(
        """SELECT o.species_id, s.common_name, s.scientific_name, s.class_name, COUNT(*)::integer AS records,
                  verified.iucn_category AS official_category, verified.taxon_level, s.current_iucn_status AS reported_category,
                  p.predicted_probability
           FROM occurrences AS o JOIN species AS s ON s.species_id = o.species_id
           LEFT JOIN LATERAL (SELECT ca.iucn_category, ca.taxon_level FROM conservation_assessments AS ca
                              WHERE ca.species_id = s.species_id ORDER BY ca.assessment_year DESC LIMIT 1) AS verified ON TRUE
           LEFT JOIN species_risk_predictions AS p ON p.species_id = s.species_id
                AND p.model_version = (SELECT model_version FROM model_registry WHERE is_current LIMIT 1)
           WHERE o.state = %(state)s
           GROUP BY o.species_id, s.common_name, s.scientific_name, s.class_name, verified.iucn_category, verified.taxon_level,
                    s.current_iucn_status, p.predicted_probability
           ORDER BY records DESC""",
        {"state": state},
    )
    threatened_official = [s for s in species if s["official_category"] in {"CR", "EN", "VU"}]
    threatened_reported = [s for s in species if not s["official_category"] and s["reported_category"] in {"CR", "EN", "VU"}]
    by_group: dict[str, int] = {}
    for item in species:
        by_group[item["class_name"] or "unknown"] = by_group.get(item["class_name"] or "unknown", 0) + 1

    last_complete = date.today().year - 1
    trend = fetch_all(
        """SELECT year, COUNT(*)::integer AS records, COUNT(DISTINCT species_id)::integer AS species
           FROM occurrences WHERE state = %(state)s AND year BETWEEN %(start)s AND %(end)s GROUP BY year ORDER BY year""",
        {"state": state, "start": last_complete - 9, "end": last_complete},
    )
    protection = fetch_all(
        """SELECT ROUND((100 * ST_Area(ST_Intersection(st.geom, ST_MakeValid(ST_Union(pa.geom)))::geography)
                         / ST_Area(st.geom::geography))::numeric, 2)::float AS wildlife_pa_area_pct,
                  COUNT(DISTINCT pa.protected_area_id)::integer AS wildlife_pas
           FROM reference_states AS st JOIN protected_areas AS pa
             ON pa.pa_class = 'wildlife_pa' AND ST_Intersects(pa.geom, st.geom)
           WHERE st.state = %(state)s GROUP BY st.geom""",
        {"state": state},
    )
    record_protection = fetch_all(
        """SELECT COUNT(*)::integer AS precise, COUNT(*) FILTER (WHERE EXISTS (
                      SELECT 1 FROM protected_areas AS pa WHERE pa.pa_class = 'wildlife_pa' AND ST_Intersects(pa.geom, o.geom)))::integer AS inside
           FROM occurrences AS o WHERE o.state = %(state)s AND o.coordinate_uncertainty_class IN ('precise', 'moderate')""",
        {"state": state},
    )[0]
    priority_cells = (cipi(None, 5, state) or {}).get("cells", [])

    sections: dict[str, list[dict[str, Any]]] = {}
    sections["biodiversity_overview"] = [
        _statement(f"{overview['records']:,} GBIF occurrence records for {overview['species']} tracked species are attributed to {state}, "
                   f"spanning {overview['first_year']}-{overview['last_year']}.", **overview),
        _statement(f"{overview['precise_records']:,} of these records ({100 * overview['precise_records'] / overview['records']:.1f}%) are located to within 10 km.",
                   precise_records=overview["precise_records"], records=overview["records"]),
    ]
    sections["species_richness"] = [
        _statement(f"Observed tracked species by group: " + ", ".join(f"{group} {count}" for group, count in sorted(by_group.items(), key=lambda x: -x[1])) + ".",
                   species_by_group=by_group),
    ]
    sections["threatened_species"] = [
        _statement(f"{len(threatened_official)} species with records here are officially threatened (IUCN CR/EN/VU): "
                   + (", ".join(f"{s['common_name'] or s['scientific_name']} ({s['official_category']}{', ' + s['taxon_level'] if s['taxon_level'] != 'species' else ''})"
                                for s in threatened_official) or "none") + ".",
                   species=[{"species_id": s["species_id"], "category": s["official_category"], "taxon_level": s["taxon_level"]} for s in threatened_official]),
    ]
    if threatened_reported:
        sections["threatened_species"].append(_statement(
            f"{len(threatened_reported)} further species are threatened according to the project's unverified reference list: "
            + ", ".join(f"{s['common_name']} ({s['reported_category']})" for s in threatened_reported) + ".",
            species=[{"species_id": s["species_id"], "source_reported_category": s["reported_category"]} for s in threatened_reported]))
    sections["notable_species"] = [
        _statement("Most recorded species: " + ", ".join(f"{s['common_name'] or s['scientific_name']} ({s['records']:,})" for s in species[:5]) + ".",
                   top_species=[{"species_id": s["species_id"], "records": s["records"]} for s in species[:5]]),
    ]
    if trend:
        first, last = trend[0], trend[-1]
        sections["temporal_trends"] = [
            _statement(f"Records per year went from {first['records']:,} in {first['year']} to {last['records']:,} in {last['year']}. "
                       "This reflects recording effort as much as wildlife and is not a population trend.", annual=trend),
        ]
    if protection:
        sections["protection_coverage"] = [
            _statement(f"Wildlife protected areas (OpenStreetMap national parks, sanctuaries and reserves) cover {protection[0]['wildlife_pa_area_pct']}% of {state}'s area "
                       f"({protection[0]['wildlife_pas']} areas intersect the state).", **protection[0]),
        ]
    if record_protection["precise"]:
        sections.setdefault("protection_coverage", []).append(_statement(
            f"{100 * record_protection['inside'] / record_protection['precise']:.1f}% of precisely located records fall inside these areas "
            f"({record_protection['inside']:,} of {record_protection['precise']:,}); this is not a measure of habitat protection.", **record_protection))
    risky = sorted((s for s in species if s["predicted_probability"] is not None), key=lambda s: -s["predicted_probability"])[:5]
    sections["risk_indicators"] = [
        _statement("Highest model-predicted vulnerability among species recorded here (MODEL PREDICTION, not IUCN status): "
                   + ", ".join(f"{s['common_name'] or s['scientific_name']} ({s['predicted_probability']:.2f})" for s in risky) + ".",
                   predictions=[{"species_id": s["species_id"], "predicted_probability": s["predicted_probability"]} for s in risky]),
    ]
    if priority_cells:
        sections["conservation_priority"] = [
            _statement(f"Top experimental CIPI grid cells in {state} (equal-weight reference): "
                       + "; ".join(f"cell near {c['centroid_lat']}N {c['centroid_lon']}E (overall rank {c['rank']}, median rank across weightings {c['sensitivity']['median_rank']:.0f})"
                                   for c in priority_cells[:3]) + ".",
                       cells=[{"cell_id": c["cell_id"], "rank": c["rank"], "components": c["components"]} for c in priority_cells[:3]]),
        ]
    sections["environmental_pressures"] = _pressure_statements(state)

    generated = datetime.now(timezone.utc).isoformat()
    report = {
        "region": state,
        "region_level": "state",
        "generated_at": generated,
        "sections": sections,
        "sources": ["GBIF occurrence download https://doi.org/10.15468/dl.dvgq2s", "IUCN Red List export retrieved 2026-10-21",
                    "OpenStreetMap contributors (ODbL)",
                    "Hansen et al. Global Forest Change 2000-2024 v1.12 (CC BY 4.0)", "GHSL R2023A built-up and population 2020 (CC BY 4.0)", "BioIndia risk model (current version) and experimental CIPI"],
        "method_note": "All statements are filled from database queries by fixed templates; each carries its evidence.",
    }
    report["markdown"] = to_markdown(report)
    return report


def to_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Biodiversity report: {report['region']}", "", f"_Generated {report['generated_at'][:10]} from platform data._", ""]
    for section, statements in report["sections"].items():
        lines += [f"## {section.replace('_', ' ').capitalize()}", ""]
        lines += [f"- {statement['text']}" for statement in statements]
        lines.append("")
    lines += ["## Sources", ""] + [f"- {source}" for source in report["sources"]]
    return "\n".join(lines)
