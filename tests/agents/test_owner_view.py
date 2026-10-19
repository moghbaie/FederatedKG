"""Owner-only graph view and local contradiction detection."""
from __future__ import annotations

import pytest

from agents.common.app.contradictions import local_pairs
from agents.common.app.graph import load_private_graph
from agents.common.app.owner_view import owner_graph
from tests.conftest import DATA, GRAPH_PERSONAS


@pytest.fixture(scope="module")
def graphs(tmp_path_factory):
    return {p: load_private_graph(p, DATA / "private" / f"{p}.ttl", tmp_path_factory.mktemp(p)) for p in GRAPH_PERSONAS}


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_local_contradictions_match_ground_truth(graphs, ground_truth, persona):
    got = {"|".join(p["pair"]): p["label"] for p in local_pairs(graphs[persona])}
    assert got == ground_truth["local_contradictions"][persona]


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_only_published_topics_are_public(graphs, public_profiles, persona):
    view = owner_graph(graphs[persona], persona)
    published = next(r["published_topics"] for r in public_profiles["researchers"] if r["researcher_id"] == persona)
    public = sorted(n["normalized_id"] for n in view["nodes"] if n["visibility"] == "public")
    assert public == sorted(published)
    assert all(n["type"] == "Topic" for n in view["nodes"] if n["visibility"] == "public")


def test_owner_view_shape(graphs, ground_truth):
    view = owner_graph(graphs["persona_a"], "persona_a")
    stats = ground_truth["graph_stats"]["persona_a"]
    assert len(view["nodes"]) == stats["entities"] + 1  # + the graph root node
    assert len(view["edges"]) == stats["relationships"]
    assert len(view["hypotheses"]) == stats["hypotheses"] and len(view["observations"]) == stats["observations"]
