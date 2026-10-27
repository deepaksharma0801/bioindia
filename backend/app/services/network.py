"""Phase 16: documented interaction networks (GloBI) and NetworkX metrics.

Language follows the roadmap: high-centrality species are 'potentially structurally important',
never 'keystone'; co-occurrence is reported separately and never counted as an interaction.
"""

from __future__ import annotations

from typing import Any

from .db import fetch_all


NOTES = [
    "Interactions come from GloBI literature and dataset records anywhere in the species' range, not from observations in India.",
    "Missing links mean no documented interaction was found, not that none exists; documented interaction data are sparse for many species.",
    "Co-occurrence associations are listed separately and are never treated as ecological interactions.",
]


def species_network(species_id: str) -> dict[str, Any] | None:
    species = fetch_all("SELECT species_id, scientific_name, common_name FROM species WHERE species_id = %(id)s", {"id": species_id})
    if not species:
        return None
    rows = fetch_all(
        """SELECT CASE WHEN source_species_id = %(id)s THEN 'outgoing' ELSE 'incoming' END AS direction,
                  interaction_type, evidence_type,
                  CASE WHEN source_species_id = %(id)s THEN target_taxon_name ELSE source_taxon_name END AS partner_name,
                  CASE WHEN source_species_id = %(id)s THEN target_species_id ELSE source_species_id END AS partner_species_id,
                  COUNT(*)::integer AS records,
                  COUNT(DISTINCT COALESCE(reference, dataset_citation))::integer AS distinct_citations
           FROM species_interactions
           WHERE source_species_id = %(id)s OR target_species_id = %(id)s
           GROUP BY 1, 2, 3, 4, 5
           ORDER BY evidence_type, records DESC, partner_name""",
        {"id": species_id},
    )
    documented = [row for row in rows if row["evidence_type"] == "DOCUMENTED"]
    for row in rows:
        row["citation_recorded"] = row["distinct_citations"] > 0
    by_type: dict[str, int] = {}
    partners: dict[str, dict[str, Any]] = {}
    for row in documented:
        by_type[row["interaction_type"]] = by_type.get(row["interaction_type"], 0) + 1
        partner = partners.setdefault(row["partner_name"], {"name": row["partner_name"], "species_id": row["partner_species_id"], "records": 0, "types": set()})
        partner["records"] += row["records"]
        partner["types"].add(row["interaction_type"])
    top_partners = [{**p, "types": sorted(p["types"])} for p in sorted(partners.values(), key=lambda p: (-p["records"], p["name"]))[:10]]
    return {
        "species": species[0],
        "documented_partner_count": len({row["partner_name"] for row in documented}),
        "partners_in_platform": sorted({row["partner_species_id"] for row in documented if row["partner_species_id"] and row["partner_species_id"] != species_id}),
        "documented_links_by_type": by_type,
        "top_partners": top_partners,
        "documented_interactions": documented,
        "co_occurrence_associations": [row for row in rows if row["evidence_type"] != "DOCUMENTED"],
        "data_sparsity": "no documented interactions found" if not documented else ("sparse (fewer than 5 partners)" if len({r["partner_name"] for r in documented}) < 5 else "documented"),
        "source": "Global Biotic Interactions (GloBI)",
        "notes": NOTES,
    }


def ecosystem_network(state: str) -> dict[str, Any] | None:
    """Documented interactions among platform species recorded in a state, with NetworkX metrics."""
    import networkx as nx
    from networkx.algorithms.community import greedy_modularity_communities

    nodes = fetch_all(
        """SELECT s.species_id, s.scientific_name, s.common_name, COUNT(o.*)::integer AS records
           FROM occurrences AS o JOIN species AS s ON s.species_id = o.species_id
           WHERE o.state = %(state)s GROUP BY s.species_id ORDER BY records DESC""",
        {"state": state},
    )
    if not nodes:
        return None
    ids = [node["species_id"] for node in nodes]
    edges = fetch_all(
        """SELECT source_species_id, target_species_id, interaction_type,
                  COUNT(DISTINCT COALESCE(reference, dataset_citation))::integer AS distinct_citations
           FROM species_interactions
           WHERE evidence_type = 'DOCUMENTED' AND source_species_id = ANY(%(ids)s) AND target_species_id = ANY(%(ids)s)
             AND source_species_id <> target_species_id
           GROUP BY 1, 2, 3""",
        {"ids": ids},
    )
    graph = nx.Graph()
    graph.add_nodes_from(ids)
    for edge in edges:
        graph.add_edge(edge["source_species_id"], edge["target_species_id"])
    linked = [node for node in graph.nodes if graph.degree(node) > 0]
    betweenness = nx.betweenness_centrality(graph) if graph.number_of_edges() else {node: 0.0 for node in graph.nodes}
    communities = list(greedy_modularity_communities(graph.subgraph(linked))) if graph.number_of_edges() else []
    community_of = {node: index for index, members in enumerate(communities) for node in members}
    ranked = sorted(linked, key=lambda node: (-betweenness[node], -graph.degree(node), node))
    return {
        "region": state,
        "nodes": [
            {**node, "degree": graph.degree(node["species_id"]), "betweenness": round(betweenness[node["species_id"]], 4),
             "community": community_of.get(node["species_id"])}
            for node in nodes
        ],
        "edges": edges,
        "metrics": {
            "species_recorded": graph.number_of_nodes(),
            "species_with_documented_links": len(linked),
            "documented_links": graph.number_of_edges(),
            "connected_components_among_linked": nx.number_connected_components(graph.subgraph(linked)) if linked else 0,
            "density": round(nx.density(graph), 4),
            "communities": len(communities),
        },
        "potentially_structurally_important_species": ranked[:5],
        "terminology": "Ranked by betweenness then degree: 'potentially structurally important', not keystone species.",
        "scope": "Only interactions between platform species recorded in this state; partners outside the platform species list are not shown.",
        "notes": NOTES,
    }
