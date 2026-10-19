"""Stage 1 discovery ranking over *published* topic identifiers only (`topic_similarity`)."""
from __future__ import annotations


def topic_similarity(a: set[str], b: set[str]) -> dict:
    union = a | b
    return {
        "metric": "topic_similarity/jaccard",
        "score": round(len(a & b) / len(union), 6) if union else 0.0,
        "matched_topics": sorted(a & b),
    }
