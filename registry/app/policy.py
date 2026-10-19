"""Comparison scope contract and policy compatibility rules (v1).

A scope says which published concepts are eligible, what is computed, by which privacy protocol,
and what may be disclosed. Compatibility is re-checked at approval, on every policy change, and
(Phase 4) at execution and release.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NORMALIZATION = "fkg-norm/1.0"
DISCLOSURE_RANK = {"score_only": 0, "summary": 1, "evidence": 2}
RESULT_VISIBILITY = ("requester_only", "both")
ENTITY_CLASSES = ("Protein", "Interaction")


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topics: list[str] = Field(min_length=1)
    entity_classes: list[Literal["Protein", "Interaction"]] = Field(min_length=1)
    metric: Literal["jaccard", "overlap_count"] = "jaccard"
    protocol: Literal["psi_ca", "plaintext_dev"] = "psi_ca"
    disclosure: Literal["score_only", "summary", "evidence"] = "score_only"
    normalization: Literal["fkg-norm/1.0"] = NORMALIZATION

    def canonical(self) -> dict:
        return {**self.model_dump(), "topics": sorted(set(self.topics)),
                "entity_classes": sorted(set(self.entity_classes))}


def fingerprint(scope: dict) -> str:
    """Stable identity of a scope, used for duplicate detection and per-pair scope quotas."""
    return hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Policy(BaseModel):
    """The owner-side settings a request must fit (a channel policy version, or v1 defaults)."""
    topics: list[str]
    max_disclosure: str = "score_only"
    allowed_result_visibility: list[str] = list(RESULT_VISIBILITY)


def incompatibility(scope: dict, result_visibility: str, policy: Policy) -> str | None:
    """Return a reason code if the request does not fit the policy, else None."""
    if not set(scope["topics"]) <= set(policy.topics):
        return "topic_outside_policy"
    if DISCLOSURE_RANK[scope["disclosure"]] > DISCLOSURE_RANK[policy.max_disclosure]:
        return "disclosure_exceeds_policy"
    if result_visibility not in policy.allowed_result_visibility:
        return "result_visibility_not_allowed"
    return None
