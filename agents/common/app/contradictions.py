"""Local contradiction detection over the agent's own synthetic observations (v1: never shared).

Two observations about the same normalized (subject, object) are classified as:
  supporting               same effect under the same experimental context
  contradictory_candidate  opposite polarity (increases vs decreases) under the same context
  context_mismatch         differing effect, but under different contexts
  insufficient_information either observation lacks context
A contradiction candidate is not proof that either observation is wrong.
"""
from __future__ import annotations

from itertools import combinations

from rdflib import Graph
from rdflib.namespace import RDF

from .graph import FKG

OPPOSITE = {("increases", "decreases"), ("decreases", "increases")}
CONTEXT_FIELDS = (FKG.cellType, FKG.treatment, FKG.timepoint)


def observations(g: Graph) -> list[dict]:
    out = []
    for obs in g.subjects(RDF.type, FKG.Observation):
        ctx = tuple(str(g.value(obs, f)) if g.value(obs, f) is not None else None for f in CONTEXT_FIELDS)
        out.append({
            "id": str(obs).rsplit(":", 1)[-1],
            "subject": str(g.value(g.value(obs, FKG.subject), FKG.normalizedId)),
            "object": str(g.value(g.value(obs, FKG.object), FKG.normalizedId)),
            "effect": str(g.value(obs, FKG.effect)),
            "context": None if all(c is None for c in ctx) else dict(zip(("cell_type", "treatment", "timepoint"), ctx)),
            "confidence": float(g.value(obs, FKG.confidence)),
        })
    return sorted(out, key=lambda o: o["id"])


def classify(a: dict, b: dict) -> str:
    if a["context"] is None or b["context"] is None:
        return "insufficient_information"
    if a["context"] != b["context"]:
        return "context_mismatch"
    if a["effect"] == b["effect"]:
        return "supporting"
    if (a["effect"], b["effect"]) in OPPOSITE:
        return "contradictory_candidate"
    return "context_mismatch"


def local_pairs(g: Graph) -> list[dict]:
    obs = observations(g)
    pairs = []
    for a, b in combinations(obs, 2):
        if (a["subject"], a["object"]) == (b["subject"], b["object"]):
            pairs.append({"pair": [a["id"], b["id"]], "label": classify(a, b)})
    return pairs
