"""The owner's own view of their private graph ("My KG"). Served only to the owner's user session.

The registry never sees this: the browser reaches the agent through the frontend proxy, and the
agent accepts only a registry-signed user token whose subject is this agent's own persona.
"""
from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS

from .contradictions import local_pairs, observations
from .graph import FKG

NODE_TYPES = {FKG.Protein: "Protein", FKG.Method: "Method", FKG.Topic: "Topic"}
EDGE_TYPES = {FKG.interactsWith: "interactsWith", FKG.measuredBy: "measuredBy", FKG.coversTopic: "coversTopic"}


def owner_graph(g: Graph, agent_id: str) -> dict:
    root = URIRef(f"urn:fkg:graph:{agent_id}")
    nodes = [{"id": str(root), "label": "My knowledge graph", "type": "Graph", "visibility": "private"}]
    for rdf_type, kind in NODE_TYPES.items():
        for s in sorted(g.subjects(RDF.type, rdf_type)):
            nodes.append({"id": str(s), "label": str(g.value(s, RDFS.label)), "type": kind,
                          # Topics are identified by their controlled-vocabulary IRI (urn:fkg:topic:<id>).
                          "normalized_id": str(g.value(s, FKG.normalizedId) or str(s).removeprefix("urn:fkg:topic:")),
                          # Only explicitly published topics are public; everything else stays private.
                          "visibility": str(g.value(s, FKG.visibility) or "private")})
    edges = [{"source": str(s), "target": str(o), "type": kind}
             for pred, kind in EDGE_TYPES.items() for s, o in sorted(g.subject_objects(pred))]
    hypotheses = [{"id": str(h).rsplit(":", 1)[-1], "text": str(g.value(h, RDFS.label))}
                  for h in sorted(g.subjects(RDF.type, FKG.Hypothesis))]
    return {"owner": agent_id, "nodes": nodes, "edges": edges, "hypotheses": hypotheses,
            "observations": observations(g), "local_contradictions": local_pairs(g),
            "notice": "Served by your own agent. The registry never receives this graph."}
