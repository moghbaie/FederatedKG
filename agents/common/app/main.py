"""FederatedKG researcher agent (Phase 1: private store loading and health only).

Each agent instance serves exactly one persona. Its private graph is read from a read-only
fixture mount and persisted to its own named volume; nothing here returns graph content.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import FastAPI
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF

AGENT_ID = os.environ["AGENT_ID"]
FIXTURE = Path(os.environ.get("GRAPH_FIXTURE", "/fixtures/graph.ttl"))
STORE_DIR = Path(os.environ.get("STORE_DIR", "/var/lib/fkg"))
FKG = Namespace("urn:fkg:vocab:")

# No interactive docs or schema: the agent surface is internal and minimal by design.
app = FastAPI(title=f"FederatedKG agent {AGENT_ID}", version="0.1.0",
              docs_url=None, redoc_url=None, openapi_url=None)
_graph = Graph()


def load_private_graph() -> Graph:
    store_file = STORE_DIR / "graph.ttl"
    if not store_file.exists():
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FIXTURE, store_file)
    g = Graph()
    g.parse(store_file, format="turtle")
    graph_node = URIRef(f"urn:fkg:graph:{AGENT_ID}")
    # Refuse to serve a graph owned by a different persona (mis-mounted volume).
    if (graph_node, RDF.type, FKG.KnowledgeGraph) not in g or \
            (graph_node, FKG.owner, Literal(AGENT_ID)) not in g:
        raise RuntimeError("private store does not belong to this agent")
    return g


@app.on_event("startup")
def _startup() -> None:
    global _graph
    _graph = load_private_graph()


@app.get("/internal/health")
def health() -> dict:
    # Deliberately content-free: no counts, labels or identifiers from the private graph.
    return {"service": "agent", "agent_id": AGENT_ID, "status": "ok", "graph_loaded": len(_graph) > 0}
