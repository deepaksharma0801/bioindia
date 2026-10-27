"""Phase 17: extinction cascade SCENARIO SIMULATION over documented interactions (GloBI).

Rules (explicit, so every result can be traced):
  * Dependencies come only from documented interaction types with a clear direction (DEPENDENCY_RULES).
    Vague types (interactsWith, visits, ecologicallyRelatedTo, kills) are not treated as dependencies.
  * The selected species is removed. In each step, any taxon that has lost at least `threshold` of
    its documented resources/hosts is marked as potentially secondarily lost, and removal propagates.
  * Results are scenario outputs, not predictions of real extinctions. Interaction records are global
    literature, incomplete for most taxa, and taxa with a single documented resource are flagged.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .db import fetch_all


# interaction_type -> who depends on whom: "source" means the source taxon depends on the target.
DEPENDENCY_RULES = {
    "eats": "source", "preysOn": "source", "symbiontOf": "source", "hasRoost": "source",
    "hasArbuscularMycorrhizalHost": "source", "hasEctomycorrhizalHost": "source", "parasitoidOf": "source", "epiphyteOf": "source",
    "hostOf": "target", "hasPathogen": "target", "hasParasite": "target", "hasEctoparasite": "target",
    "hasEndoparasite": "target", "hasParasitoid": "target", "reservoirHostOf": "target", "roostOf": "target",
    "arbuscularMycorrhizalHostOf": "target", "ectomycorrhizalHostOf": "target", "hasEpiphyte": "target",
    "pollinates": "both", "visitsFlowersOf": "both",
}
DEFAULT_THRESHOLD = 0.5
SENSITIVITY_THRESHOLDS = (0.25, 0.5, 0.75)
ASSUMPTIONS = [
    "Dependencies are only the documented interaction records in GloBI; undocumented links are absent, so effects are likely underestimated for poorly studied taxa.",
    "A taxon is marked potentially secondarily lost when it loses at least the threshold share of its documented resources or hosts; real species can switch resources.",
    "Interaction records come from anywhere in the species' range, not specifically India.",
    "Pollination and flower visiting are treated as mutual dependency.",
    "Taxa with a single documented resource are flagged low-confidence: losing it counts as 100% loss.",
]


class SimulationError(ValueError):
    """Unsupported simulation request (unknown species or region, invalid parameters)."""


def _node(species_id: str | None, name: str) -> str:
    return species_id or name


def _dependencies(region_species: set[str] | None) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Map each taxon to the set of taxa it depends on; also return display labels."""
    rows = fetch_all(
        """SELECT source_species_id, source_taxon_name, interaction_type, target_species_id, target_taxon_name
           FROM species_interactions WHERE evidence_type = 'DOCUMENTED' AND interaction_type = ANY(%(types)s)""",
        {"types": list(DEPENDENCY_RULES)},
    )
    dependencies: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for row in rows:
        source = _node(row["source_species_id"], row["source_taxon_name"])
        target = _node(row["target_species_id"], row["target_taxon_name"])
        if source == target:
            continue
        # Platform species not recorded in the chosen region are not part of that region's network.
        if region_species is not None and any(
            species_id and species_id not in region_species for species_id in (row["source_species_id"], row["target_species_id"])
        ):
            continue
        labels.setdefault(source, row["source_taxon_name"])
        labels.setdefault(target, row["target_taxon_name"])
        direction = DEPENDENCY_RULES[row["interaction_type"]]
        if direction in {"source", "both"}:
            dependencies[source].add(target)
        if direction in {"target", "both"}:
            dependencies[target].add(source)
    return dependencies, labels


def _cascade(dependencies: dict[str, set[str]], start: str, threshold: float, max_steps: int) -> list[set[str]]:
    removed, steps = {start}, []
    for _ in range(max_steps):
        newly = {
            node for node, resources in dependencies.items()
            if node not in removed and resources and len(resources & removed) / len(resources) >= threshold
        }
        if not newly:
            break
        steps.append(newly)
        removed |= newly
    return steps


def _structure(dependencies: dict[str, set[str]], nodes: set[str]) -> dict[str, Any]:
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from((a, b) for a, resources in dependencies.items() for b in resources if a in nodes and b in nodes)
    components = list(nx.connected_components(graph)) if graph.number_of_nodes() else []
    largest = max((len(c) for c in components), default=0)
    return {
        "taxa": graph.number_of_nodes(),
        "dependency_links": graph.number_of_edges(),
        "connected_components": len(components),
        "largest_component_share": round(largest / graph.number_of_nodes(), 4) if graph.number_of_nodes() else 0.0,
    }


def extinction_cascade(species_id: str, region: str | None = None, threshold: float = DEFAULT_THRESHOLD, max_steps: int = 3) -> dict[str, Any]:
    if not 0 < threshold <= 1:
        raise SimulationError("threshold must be between 0 (exclusive) and 1.")
    if not 1 <= max_steps <= 10:
        raise SimulationError("max_steps must be between 1 and 10.")
    species = fetch_all("SELECT species_id, scientific_name, common_name FROM species WHERE species_id = %(id)s", {"id": species_id})
    if not species:
        raise SimulationError(f"Species '{species_id}' was not found.")
    region_species = None
    if region:
        region_species = {row["species_id"] for row in fetch_all("SELECT DISTINCT species_id FROM occurrences WHERE state = %(state)s", {"state": region})}
        if not region_species:
            raise SimulationError(f"No occurrence records for region '{region}'.")
        if species_id not in region_species:
            raise SimulationError(f"Species '{species_id}' has no records in region '{region}'.")

    dependencies, labels = _dependencies(region_species)
    dependents = {node for node, resources in dependencies.items() if species_id in resources}
    if species_id not in labels:
        return {
            "label": "SCENARIO SIMULATION",
            "species": species[0], "region": region,
            "result": "no documented dependency links for this species; no cascade can be simulated",
            "assumptions": ASSUMPTIONS,
        }

    steps = _cascade(dependencies, species_id, threshold, max_steps)
    lost = set().union(*steps) if steps else set()
    # Local network: the species, its direct partners and their partners (2 steps out).
    neighbours = {species_id} | dependents | dependencies.get(species_id, set())
    local = set(neighbours)
    for node in neighbours:
        local |= dependencies.get(node, set())
        local |= {other for other, resources in dependencies.items() if node in resources}
    before = _structure(dependencies, local)
    after = _structure(dependencies, local - lost - {species_id})

    def describe(node: str) -> dict[str, Any]:
        resources = dependencies.get(node, set())
        return {
            "taxon": labels.get(node, node),
            # Platform species are keyed by species_id; every other taxon by its name.
            "platform_species_id": node if node != labels.get(node) else None,
            "documented_resources": len(resources),
            "share_of_resources_lost": round(len(resources & (lost | {species_id})) / len(resources), 3) if resources else None,
            "low_confidence_single_resource": len(resources) == 1,
        }

    lost_details = [describe(node) for node in lost]
    return {
        "label": "SCENARIO SIMULATION",
        "species": species[0],
        "region": region,
        "parameters": {"threshold": threshold, "max_steps": max_steps},
        "summary": {
            "directly_dependent_taxa": len(dependents),
            "potentially_secondarily_lost": len(lost),
            "of_which_platform_species": sorted(d["platform_species_id"] for d in lost_details if d["platform_species_id"]),
            "of_which_low_confidence_single_resource": sum(1 for d in lost_details if d["low_confidence_single_resource"]),
        },
        "directly_dependent_taxa": sorted((describe(node) for node in dependents), key=lambda d: -(d["share_of_resources_lost"] or 0)),
        "potentially_secondarily_lost": [
            {"step": step_number, "taxa": sorted((describe(node) for node in step), key=lambda d: d["taxon"])}
            for step_number, step in enumerate(steps, start=1)
        ],
        "local_network_before": before,
        "local_network_after": after,
        "connectivity_change": {
            "dependency_links_lost": before["dependency_links"] - after["dependency_links"],
            "components_change": after["connected_components"] - before["connected_components"],
            "largest_component_share_change": round(after["largest_component_share"] - before["largest_component_share"], 4),
        },
        "sensitivity": {
            f"threshold_{value}": sum(len(step) for step in _cascade(dependencies, species_id, value, max_steps))
            for value in SENSITIVITY_THRESHOLDS
        },
        "assumptions": ASSUMPTIONS,
        "uncertainty": "Counts depend strongly on how well each taxon's interactions are documented; compare the sensitivity results before interpreting.",
    }
