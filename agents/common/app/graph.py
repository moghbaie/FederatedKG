"""Private graph access. Everything here stays inside the agent."""
from __future__ import annotations

import shutil
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

FKG = Namespace("urn:fkg:vocab:")


def load_private_graph(agent_id: str, fixture: Path, store_dir: Path) -> Graph:
    store_file = store_dir / "graph.ttl"
    if not store_file.exists():
        store_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, store_file)
    g = Graph()
    g.parse(store_file, format="turtle")
    node = URIRef(f"urn:fkg:graph:{agent_id}")
    # Refuse to serve a graph owned by a different persona (mis-mounted volume).
    if (node, RDF.type, FKG.KnowledgeGraph) not in g or (node, FKG.owner, Literal(agent_id)) not in g:
        raise RuntimeError("private store does not belong to this agent")
    return g


def graph_metadata(g: Graph, agent_id: str) -> dict:
    node = URIRef(f"urn:fkg:graph:{agent_id}")
    return {"graph": str(node), "graph_version": str(g.value(node, FKG.version)),
            "normalization": str(g.value(node, FKG.normalization))}


def eligible_sets(g: Graph, entity_classes: list[str]) -> dict[str, set[str]]:
    """Normalized identifiers per requested class.

    v1 scoping: scope topics gate *whether* a comparison is allowed (local policy); they do not
    filter entities, because fixture entities are not individually topic-tagged.
    """
    def norm(node) -> str:
        return str(g.value(node, FKG.normalizedId))

    out: dict[str, set[str]] = {}
    for cls in entity_classes:
        if cls == "Protein":
            out[cls] = {norm(s) for s in g.subjects(RDF.type, FKG.Protein)}
        elif cls == "Interaction":
            out[cls] = {"|".join(sorted((norm(a), norm(b)))) for a, b in g.subject_objects(FKG.interactsWith)}
        else:
            raise ValueError(f"unsupported entity class {cls}")
    return out
