"""Phase 16: load cached GloBI interactions into species_interactions (replacing earlier GloBI rows).

Names are reduced to the binomial and linked to platform species where they match. Co-occurrence
records are kept but labelled CO_OCCURRENCE_ASSOCIATION, never as a documented interaction.
Interaction strength and confidence are not invented; the API reports citation counts instead.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from db_schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "globi"
REPORT = ROOT / "data" / "analytics" / "interaction_load_report.json"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://bioindia:bioindia@127.0.0.1:5432/bioindia")
# Spatial associations, not ecological interactions.
CO_OCCURRENCE_TYPES = {"coOccursWith", "adjacentTo"}
# GloBI reports most interactions from both ends ("A eats B" and "B eatenBy A"). Inverse forms
# are turned round to one direction so each interaction is stored once.
INVERSE_TYPES = {
    "eatenBy": "eats",
    "killedBy": "kills",
    "preyedUponBy": "preysOn",
    "hasHost": "hostOf",
    "parasiteOf": "hasParasite",
    "endoparasiteOf": "hasEndoparasite",
    "ectoparasiteOf": "hasEctoparasite",
    "pathogenOf": "hasPathogen",
    "vectorOf": "hasVector",
    "pollinatedBy": "pollinates",
    "flowersVisitedBy": "visitsFlowersOf",
    "dispersalVectorOf": "hasDispersalVector",
    "kleptoparasiteOf": "hasKleptoparasite",
}


def binomial(name: str | None) -> str | None:
    parts = (name or "").replace("(", " ").replace(")", " ").split()
    if len(parts) < 2 or not parts[0][:1].isupper() or not parts[1].islower():
        return None
    if parts[1].rstrip(".") in {"sp", "spp", "cf", "aff"}:
        return None
    return f"{parts[0]} {parts[1]}"


def evidence_type(interaction_type: str) -> str:
    return "CO_OCCURRENCE_ASSOCIATION" if interaction_type in CO_OCCURRENCE_TYPES else "DOCUMENTED"


def normalise(row: dict[str, object], species_by_name: dict[str, str], retrieved_at: str) -> dict[str, object] | None:
    source, target, kind = row.get("source_taxon_name"), row.get("target_taxon_name"), row.get("interaction_type")
    if not source or not target or not kind:
        return None
    target_path = row.get("target_taxon_path") or None
    if kind in INVERSE_TYPES:
        source, target, kind = target, source, INVERSE_TYPES[kind]
        target_path = row.get("source_taxon_path") or None
    reference = row.get("study_citation") or None
    dataset = row.get("study_source_citation") or None
    record = {
        "source_taxon_name": source,
        "source_species_id": species_by_name.get(binomial(source) or ""),
        "interaction_type": kind,
        "target_taxon_name": target,
        "target_species_id": species_by_name.get(binomial(target) or ""),
        "target_taxon_path": target_path,
        "evidence_type": evidence_type(str(kind)),
        "reference": reference,
        "dataset_citation": dataset,
        "study_url": row.get("study_url") or None,
        "data_source": "GloBI",
        "retrieved_at": retrieved_at,
    }
    if not record["source_species_id"] and not record["target_species_id"]:
        return None
    material = "|".join(str(record[key] or "") for key in ("source_taxon_name", "interaction_type", "target_taxon_name", "reference", "dataset_citation"))
    record["interaction_id"] = hashlib.sha1(material.encode("utf-8")).hexdigest()
    return record


def main() -> None:
    ensure_schema(DATABASE_URL)
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT species_id, scientific_name, canonical_name FROM species")
            species_by_name = {}
            for species_id, scientific, canonical in cursor.fetchall():
                for name in (scientific, canonical):
                    if name:
                        species_by_name[name] = species_id

            records: dict[str, dict[str, object]] = {}
            truncated, files = [], 0
            for path in sorted(CACHE.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                files += 1
                truncated += payload.get("truncated_queries", [])
                for row in payload["rows"]:
                    record = normalise(row, species_by_name, payload["retrieved_at"])
                    if record:
                        records[record["interaction_id"]] = record

            cursor.execute("DELETE FROM species_interactions WHERE data_source = 'GloBI'")
            columns = list(next(iter(records.values())).keys()) if records else []
            if records:
                cursor.executemany(
                    f"INSERT INTO species_interactions ({', '.join(columns)}) VALUES ({', '.join('%(' + c + ')s' for c in columns)})",
                    list(records.values()),
                )
            cursor.execute("""
                SELECT COUNT(DISTINCT s) FROM (
                    SELECT source_species_id AS s FROM species_interactions WHERE evidence_type = 'DOCUMENTED'
                    UNION SELECT target_species_id FROM species_interactions WHERE evidence_type = 'DOCUMENTED') x
                WHERE s IS NOT NULL""")
            species_with_interactions = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM species")
            species_total = cursor.fetchone()[0]

    values = list(records.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Global Biotic Interactions (GloBI), https://www.globalbioticinteractions.org",
        "species_files": files,
        "interactions_loaded": len(values),
        "by_evidence_type": dict(Counter(r["evidence_type"] for r in values)),
        "by_interaction_type": dict(Counter(r["interaction_type"] for r in values).most_common(15)),
        "between_two_platform_species": sum(1 for r in values if r["source_species_id"] and r["target_species_id"]),
        "platform_species_with_documented_interactions": species_with_interactions,
        "platform_species_total": species_total,
        "truncated_queries": truncated,
        "notes": [
            "Interactions are literature and dataset records from anywhere in the species' range, not observations in India.",
            "Absence of a record means no documented interaction was found, not that none exists.",
            "No interaction strength or confidence score is assigned; citation counts are reported instead.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
