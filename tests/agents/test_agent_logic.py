"""Agent-side logic that runs without the PSI library: set extraction, plaintext oracle, local policy."""
from __future__ import annotations

import json
from itertools import combinations

import pytest

from agents.common.app.graph import eligible_sets, graph_metadata, load_private_graph
from agents.common.app.local_policy import AgentState, LocalPolicy
from similarity.scoped_baseline import plaintext_overlap
from tests.conftest import DATA, GRAPH_PERSONAS, ROOT


@pytest.fixture(scope="module")
def sets(tmp_path_factory):
    out = {}
    for p in GRAPH_PERSONAS:
        g = load_private_graph(p, DATA / "private" / f"{p}.ttl", tmp_path_factory.mktemp(p))
        out[p] = eligible_sets(g, ["Protein", "Interaction"])
    return out


def test_plaintext_oracle_matches_ground_truth_for_every_pair(sets, ground_truth):
    for a, b in combinations(GRAPH_PERSONAS, 2):
        key = f"{a}|{b}"
        inter, size_a, size_b = plaintext_overlap(sets[a]["Protein"], sets[b]["Protein"])
        gt = ground_truth["protein_overlap"][key]
        assert (inter, [size_a, size_b]) == (gt["intersection"], gt["set_sizes"]), key
        inter, size_a, size_b = plaintext_overlap(sets[a]["Interaction"], sets[b]["Interaction"])
        gt = ground_truth["interaction_overlap"][key]
        assert (inter, size_a + size_b - inter) == (gt["intersection"], gt["union"]), key


def test_agent_refuses_foreign_graph(tmp_path):
    with pytest.raises(RuntimeError):
        load_private_graph("persona_a", DATA / "private" / "persona_b.ttl", tmp_path)


def test_graph_metadata_has_no_identifiers(tmp_path):
    g = load_private_graph("persona_a", DATA / "private" / "persona_a.ttl", tmp_path)
    assert graph_metadata(g, "persona_a") == {"graph": "urn:fkg:graph:persona_a", "graph_version": "1",
                                              "normalization": "fkg-norm/1.0"}


def _policy(persona="persona_c") -> LocalPolicy:
    return LocalPolicy.load(ROOT / "agents" / persona / "policy.json")


def _ticket(**scope_over) -> dict:
    scope = {"topics": ["interactomics"], "entity_classes": ["Protein"], "metric": "jaccard", "protocol": "psi_ca",
             "disclosure": "summary", "normalization": "fkg-norm/1.0", **scope_over}
    return {"scope": scope}


@pytest.mark.parametrize("over,reason", [
    ({}, None),
    ({"topics": ["chromatin_regulation"]}, "local_topic_not_allowed"),    # persona_c private topic
    ({"topics": ["host_pathogen"]}, "local_topic_not_allowed"),           # not persona_c's topic
    ({"disclosure": "evidence"}, "local_disclosure_not_allowed"),
    ({"protocol": "plaintext_dev"}, "local_protocol_not_allowed"),        # env flag off
    ({"normalization": "other/1"}, "local_normalization_mismatch"),
    ({"entity_classes": ["Gene"]}, "local_entity_class_not_allowed"),
])
def test_local_policy_is_independent(over, reason):
    assert _policy().refusal(_ticket(**over), dev_plaintext_enabled=False) == reason


def test_every_persona_policy_allows_only_published_topics(public_profiles):
    published = {r["researcher_id"]: r["published_topics"] for r in public_profiles["researchers"]}
    for p in GRAPH_PERSONAS:
        assert _policy(p).allowed_topics == published[p]


def test_single_use_claims_persist(tmp_path):
    state = AgentState(tmp_path / "state.json")
    assert state.claim("t1:client:persona_a") is True
    assert state.claim("t1:client:persona_a") is False
    assert AgentState(tmp_path / "state.json").claim("t1:client:persona_a") is False  # survives restart


def test_pair_limit_counts_each_ticket_once(tmp_path):
    state = AgentState(tmp_path / "state.json")
    assert all(state.count_comparison("persona_b", f"t{i}", 1000.0, limit=3) for i in range(3))
    assert state.count_comparison("persona_b", "t0", 1000.0, limit=3) is True    # same ticket again
    assert state.count_comparison("persona_b", "t9", 1000.0, limit=3) is False
    assert state.count_comparison("persona_c", "t9", 1000.0, limit=3) is True    # other counterpart
    assert state.count_comparison("persona_b", "t9", 1000.0 + 24 * 3600 + 1, limit=3) is True  # window rolled
    saved = json.loads((tmp_path / "state.json").read_text())
    assert "P0" not in json.dumps(saved)  # no identifiers in agent state
