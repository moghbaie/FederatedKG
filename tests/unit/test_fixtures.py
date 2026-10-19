"""Fixture integrity: sizes, synthetic labelling, normalization, ground truth, determinism."""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from itertools import combinations

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from tests.conftest import DATA, GRAPH_PERSONAS, ROOT

FKG = Namespace("urn:fkg:vocab:")
REAL_SCIENTISTS = ["Matthias Mann", "Mann", "Yates", "Gingras", "Krogan"]
ACCESSION = re.compile(r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$")


@pytest.fixture(scope="module")
def graphs() -> dict[str, Graph]:
    out = {}
    for p in GRAPH_PERSONAS:
        g = Graph()
        g.parse(DATA / "private" / f"{p}.ttl", format="turtle")
        out[p] = g
    return out


def proteins(g: Graph) -> set[str]:
    return {str(g.value(s, FKG.normalizedId)) for s in g.subjects(RDF.type, FKG.Protein)}


def interactions(g: Graph) -> set[tuple[str, str]]:
    return {tuple(sorted((str(g.value(a, FKG.normalizedId)), str(g.value(b, FKG.normalizedId)))))
            for a, b in g.subject_objects(FKG.interactsWith)}


def test_regeneration_is_byte_identical():
    r = subprocess.run([sys.executable, "scripts/build_fixtures.py", "--check"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_graph_sizes_within_plan(graphs, ground_truth, persona):
    g = graphs[persona]
    entities = sum(len(set(g.subjects(RDF.type, c))) for c in (FKG.Protein, FKG.Method, FKG.Topic))
    relationships = sum(len(list(g.triples((None, p, None))))
                        for p in (FKG.interactsWith, FKG.measuredBy, FKG.coversTopic))
    hypotheses = len(set(g.subjects(RDF.type, FKG.Hypothesis)))
    observations = len(set(g.subjects(RDF.type, FKG.Observation)))
    assert 20 <= entities <= 30
    assert 30 <= relationships <= 50
    assert 3 <= hypotheses <= 5
    assert 5 <= observations <= 10
    assert ground_truth["graph_stats"][persona] == {"entities": entities, "relationships": relationships,
                                                     "hypotheses": hypotheses, "observations": observations}


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_every_node_is_synthetic_owned_and_versioned(graphs, persona):
    g = graphs[persona]
    for s in set(g.subjects(RDF.type, None)):
        assert (s, FKG.isSynthetic, Literal(True)) in g, s
        assert (s, FKG.owner, Literal(persona)) in g, s
        for field in (FKG.visibility, FKG.source, FKG.provenance, FKG.createdAt, FKG.version):
            assert g.value(s, field) is not None, (s, field)


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_hypotheses_are_labelled_synthetic(graphs, persona):
    g = graphs[persona]
    for h in g.subjects(RDF.type, FKG.Hypothesis):
        assert str(g.value(h, RDFS.label)).startswith("SYNTHETIC: ")


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_identifiers_are_normalized(graphs, ground_truth, persona):
    g = graphs[persona]
    canary = ground_truth["canaries"][persona]
    for pid in proteins(g):
        assert pid == canary or ACCESSION.match(pid), pid
    for m in g.subjects(RDF.type, FKG.Method):
        assert re.match(r"^MI:\d{4}$", str(g.value(m, FKG.normalizedId)))
    assert (URIRef(f"urn:fkg:graph:{persona}"), FKG.normalization, Literal(ground_truth["normalization"])) in g


@pytest.mark.parametrize("persona", GRAPH_PERSONAS)
def test_id_mapping_covers_every_protein(graphs, persona):
    with open(DATA / "private" / f"{persona}_id_mapping.csv", encoding="utf-8") as f:
        mapped = {r["normalized_id"] for r in csv.DictReader(f) if r["entity_class"] == "Protein"}
    assert mapped == proteins(graphs[persona])


def test_overlaps_recomputed_from_graphs_match_ground_truth(graphs, ground_truth):
    for a, b in combinations(GRAPH_PERSONAS, 2):
        key = f"{a}|{b}"
        pa, pb = proteins(graphs[a]), proteins(graphs[b])
        assert len(pa & pb) == ground_truth["protein_overlap"][key]["intersection"], key
        assert len(pa | pb) == ground_truth["protein_overlap"][key]["union"], key
        ia, ib = interactions(graphs[a]), interactions(graphs[b])
        assert len(ia & ib) == ground_truth["interaction_overlap"][key]["intersection"], key


def test_overlaps_are_intentionally_varied(ground_truth):
    counts = [v["intersection"] for v in ground_truth["protein_overlap"].values()]
    assert max(counts) >= 10, "need a strong overlap pair"
    assert min(counts) < 3, "need a low-count pair to exercise insufficient_disclosure"


def test_each_graph_has_a_fabricated_contradiction(ground_truth):
    for p in GRAPH_PERSONAS:
        assert "contradictory_candidate" in ground_truth["local_contradictions"][p].values()


def test_canaries_are_unique_to_their_graph(graphs, ground_truth):
    for p, canary in ground_truth["canaries"].items():
        assert canary in proteins(graphs[p])
        for other in GRAPH_PERSONAS:
            if other != p:
                assert canary not in (DATA / "private" / f"{other}.ttl").read_text(encoding="utf-8")


def test_public_profiles_leak_nothing_private(public_profiles, ground_truth):
    text = (DATA / "public" / "researchers.json").read_text(encoding="utf-8")
    for canary in ground_truth["canaries"].values():
        assert canary not in text
    for topics in ground_truth["private_topics"].values():
        for t in topics:
            assert t not in text
    assert "urn:fkg:graph" not in text and "uniprot" not in text.lower()


def test_real_scientists_are_only_cited_never_account_holders(public_profiles):
    ids = {r["researcher_id"] for r in public_profiles["researchers"]}
    assert ids == {"persona_a", "persona_b", "persona_c", "persona_d", "persona_e"}
    for r in public_profiles["researchers"]:
        assert r["is_simulated"] is True
        assert not any(n in r["display_name"] or n in r["theme"] for n in REAL_SCIENTISTS)
    for p in GRAPH_PERSONAS:
        ttl = (DATA / "private" / f"{p}.ttl").read_text(encoding="utf-8")
        assert not any(n in ttl for n in REAL_SCIENTISTS), p


def test_persona_e_is_the_only_unverified_account(public_profiles):
    unverified = [r["researcher_id"] for r in public_profiles["researchers"] if not r["verified_researcher"]]
    assert unverified == ["persona_e"]
