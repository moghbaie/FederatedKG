"""Deterministically generate the synthetic FederatedKG fixtures from scripts/fixture_spec.py.

Outputs:
  data/synthetic/public/researchers.json     public discovery profiles (registry may read)
  data/synthetic/public/sources.csv          citation and vocabulary provenance
  data/synthetic/private/<persona>.ttl       private graph (only its own agent may read)
  data/synthetic/private/<persona>_id_mapping.csv
  data/synthetic/ground_truth.json           test-only expected values

Usage: python scripts/build_fixtures.py [--check]
  --check  exit 1 if regenerating would change any file (used by CI).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_spec as spec  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic"

UNIPROT = "http://purl.uniprot.org/uniprot/"
OBO = "http://purl.obolibrary.org/obo/"
TOPIC = "urn:fkg:topic:"


def canary_id(persona: str) -> str:
    digest = hashlib.sha256(f"fkg-canary/{persona}/v1".encode()).hexdigest()[:12]
    return f"CANARY-{persona[-1].upper()}-{digest}"


def protein_iri(persona: str, symbol: str) -> str:
    if symbol == "CANARY":
        return f"urn:fkg:synthetic:{persona}:construct:{canary_id(persona)}"
    return UNIPROT + spec.SYMBOL_TO_ACC[symbol]


def protein_norm_id(persona: str, symbol: str) -> str:
    return canary_id(persona) if symbol == "CANARY" else spec.SYMBOL_TO_ACC[symbol]


def method_iri(mi: str) -> str:
    return OBO + mi.replace(":", "_")


def lit(value) -> str:
    if isinstance(value, bool):
        return f'"{str(value).lower()}"^^xsd:boolean'
    if isinstance(value, float):
        return f'"{value}"^^xsd:decimal'
    return json.dumps(value, ensure_ascii=False)


def meta(persona: str, visibility: str = "private") -> list[str]:
    return [
        "fkg:isSynthetic true",
        f"fkg:owner {lit(persona)}",
        f"fkg:visibility {lit(visibility)}",
        f"fkg:source {lit('synthetic fixture generator')}",
        f"fkg:provenance {lit('scripts/fixture_spec.py')}",
        f'fkg:createdAt "{spec.CREATED_AT}"^^xsd:dateTime',
        f"fkg:version {lit(spec.FIXTURE_VERSION)}",
    ]


def block(subject: str, props: list[str]) -> str:
    return f"<{subject}>\n    " + " ;\n    ".join(props) + " .\n"


def build_graph(persona: str) -> tuple[str, dict]:
    p = spec.PERSONAS[persona]
    graph_iri = f"urn:fkg:graph:{persona}"
    symbols = p["proteins"] + ["CANARY"]
    topics = p["published_topics"] + p["private_topics"]
    methods = p["methods"]
    out = [
        "# SYNTHETIC DEMONSTRATION GRAPH. Not data from any real researcher or experiment.\n",
        f"# Owner: {p['display_name']} (simulated account). Normalization: {spec.NORMALIZATION}\n",
        "@prefix fkg: <urn:fkg:vocab:> .\n",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n",
    ]
    relationships = 0

    out.append(block(graph_iri, [
        "a fkg:KnowledgeGraph",
        f"fkg:normalization {lit(spec.NORMALIZATION)}",
        *[f"fkg:coversTopic <{TOPIC}{t}>" for t in topics],
        *meta(persona),
    ]))
    relationships += len(topics)

    for t in topics:
        vis = "public" if t in p["published_topics"] else "private"
        out.append(block(TOPIC + t, ["a fkg:Topic", f"rdfs:label {lit(spec.TOPICS[t])}", *meta(persona, vis)]))
    for mi in methods:
        out.append(block(method_iri(mi), [
            "a fkg:Method", f"rdfs:label {lit(spec.METHODS[mi])}", f"fkg:normalizedId {lit(mi)}",
            *meta(persona)]))

    adjacency: dict[str, list[str]] = {s: [] for s in symbols}
    for a, b in p["interactions"]:
        adjacency[a].append(b)
    for i, s in enumerate(symbols):
        label = canary_id(persona) if s == "CANARY" else p["label_aliases"].get(s, s)
        props = [
            "a fkg:Protein",
            f"rdfs:label {lit(label)}",
            f"fkg:normalizedId {lit(protein_norm_id(persona, s))}",
            f"fkg:measuredBy <{method_iri(methods[i % len(methods)])}>",
            *[f"fkg:interactsWith <{protein_iri(persona, t)}>" for t in adjacency[s]],
            f"fkg:confidence {lit(0.9 if s != 'CANARY' else 0.5)}",
            *meta(persona),
        ]
        relationships += 1 + len(adjacency[s])
        out.append(block(protein_iri(persona, s), props))

    for n, text in enumerate(spec.HYPOTHESES[persona], start=1):
        out.append(block(f"urn:fkg:{persona}:hypothesis:h{n}", [
            "a fkg:Hypothesis", f"rdfs:label {lit('SYNTHETIC: ' + text)}", *meta(persona)]))

    for oid, s, effect, o, ctx, conf in spec.OBSERVATIONS[persona]:
        props = [
            "a fkg:Observation",
            f"fkg:subject <{protein_iri(persona, s)}>",
            f"fkg:effect {lit(effect)}",
            f"fkg:object <{protein_iri(persona, o)}>",
            f"fkg:confidence {lit(conf)}",
        ]
        if ctx:
            props += [f"fkg:cellType {lit(ctx['cell_type'])}", f"fkg:treatment {lit(ctx['treatment'])}",
                      f"fkg:timepoint {lit(ctx['timepoint'])}"]
        out.append(block(f"urn:fkg:{persona}:observation:{oid}", props + meta(persona)))

    stats = {
        "entities": len(symbols) + len(methods) + len(topics),
        "relationships": relationships,
        "hypotheses": len(spec.HYPOTHESES[persona]),
        "observations": len(spec.OBSERVATIONS[persona]),
    }
    return "\n".join(out), stats


def mapping_csv(persona: str) -> str:
    p = spec.PERSONAS[persona]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["source_label", "entity_class", "normalized_id", "normalized_label", "scheme"])
    for s in p["proteins"]:
        w.writerow([p["label_aliases"].get(s, s), "Protein", spec.SYMBOL_TO_ACC[s], s, "UniProtKB"])
    w.writerow([canary_id(persona), "Protein", canary_id(persona), "synthetic construct", "fkg-synthetic"])
    for mi in p["methods"]:
        w.writerow([spec.METHODS[mi], "Method", mi, spec.METHODS[mi], "PSI-MI"])
    for t in p["published_topics"] + p["private_topics"]:
        w.writerow([spec.TOPICS[t], "Topic", t, spec.TOPICS[t], "fkg-topic"])
    return buf.getvalue()


def researchers_json() -> str:
    profiles = []
    for pid, p in spec.PERSONAS.items():
        profiles.append({
            "researcher_id": pid,
            "display_name": p["display_name"],
            "theme": p["theme"],
            "verified_researcher": p["verified"],
            "published_topics": p["published_topics"],
            "topic_vocabulary": "fkg-topic/1.0",
            "visibility": "research" if p["verified"] else "public",
            "is_simulated": True,
            "public_scientific_inspiration": p["inspiration"],
            "disclaimer": "Simulated demonstration account. The cited scientist is a public research-theme "
                          "inspiration only and is not a user, participant, or endorser.",
        })
    return json.dumps({"normalization": spec.NORMALIZATION, "researchers": profiles}, indent=2) + "\n"


def sources_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["kind", "subject", "identifier", "url", "retrieved", "verified_via", "access_terms"])
    for pid, p in spec.PERSONAS.items():
        if p["inspiration"]:
            doi = p["inspiration"]["doi"]
            w.writerow(["citation", pid, f"doi:{doi}", f"https://doi.org/{doi}", "2026-10-19",
                        "Crossref REST API", "bibliographic metadata only"])
    w.writerow(["vocabulary", "proteins", "UniProtKB accessions", "https://rest.uniprot.org/", "2026-10-19",
                "UniProt REST API (all reviewed entries)", "UniProt: CC BY 4.0"])
    w.writerow(["vocabulary", "methods", "PSI-MI terms", "https://www.ebi.ac.uk/ols4/ontologies/mi",
                "2026-10-19", "EBI OLS4 API", "see PSI-MI license on OBO Foundry"])
    w.writerow(["vocabulary", "topics", "urn:fkg:topic:*", "", "2026-10-19", "local", "project-defined"])
    return buf.getvalue()


def jaccard(a: set, b: set) -> dict:
    inter, union = a & b, a | b
    return {"intersection": len(inter), "union": len(union),
            "jaccard": round(len(inter) / len(union), 6) if union else 0.0}


def ground_truth(stats: dict) -> str:
    gt: dict = {"normalization": spec.NORMALIZATION, "graph_stats": stats,
                "canaries": {p: canary_id(p) for p in spec.GRAPH_PERSONAS},
                "private_topics": {p: spec.PERSONAS[p]["private_topics"] for p in spec.GRAPH_PERSONAS},
                "topic_similarity": {}, "protein_overlap": {}, "interaction_overlap": {},
                "local_contradictions": {}}
    for a, b in combinations(spec.PERSONAS, 2):
        ta, tb = set(spec.PERSONAS[a]["published_topics"]), set(spec.PERSONAS[b]["published_topics"])
        gt["topic_similarity"][f"{a}|{b}"] = {**jaccard(ta, tb), "matched_topics": sorted(ta & tb)}
    for a, b in combinations(spec.GRAPH_PERSONAS, 2):
        pa = {protein_norm_id(a, s) for s in spec.PERSONAS[a]["proteins"] + ["CANARY"]}
        pb = {protein_norm_id(b, s) for s in spec.PERSONAS[b]["proteins"] + ["CANARY"]}
        gt["protein_overlap"][f"{a}|{b}"] = {**jaccard(pa, pb), "set_sizes": [len(pa), len(pb)]}
        ia = {tuple(sorted((protein_norm_id(a, x), protein_norm_id(a, y)))) for x, y in spec.PERSONAS[a]["interactions"]}
        ib = {tuple(sorted((protein_norm_id(b, x), protein_norm_id(b, y)))) for x, y in spec.PERSONAS[b]["interactions"]}
        gt["interaction_overlap"][f"{a}|{b}"] = jaccard(ia, ib)
    for p, pairs in spec.LOCAL_PAIR_LABELS.items():
        gt["local_contradictions"][p] = {f"{x}|{y}": label for (x, y), label in pairs.items()}
    return json.dumps(gt, indent=2, sort_keys=True) + "\n"


def render() -> dict[Path, str]:
    files: dict[Path, str] = {}
    stats = {}
    for persona in spec.GRAPH_PERSONAS:
        ttl, stats[persona] = build_graph(persona)
        files[DATA / "private" / f"{persona}.ttl"] = ttl
        files[DATA / "private" / f"{persona}_id_mapping.csv"] = mapping_csv(persona)
    files[DATA / "public" / "researchers.json"] = researchers_json()
    files[DATA / "public" / "sources.csv"] = sources_csv()
    files[DATA / "ground_truth.json"] = ground_truth(stats)
    return files


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, content in render().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    if check and stale:
        print("Fixtures out of date:", *stale, sep="\n  ")
        return 1
    print("wrote" if stale and not check else "up to date", len(stale), "file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
