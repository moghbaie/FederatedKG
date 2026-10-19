"""`plaintext-dev` scoped-set matcher: correctness oracle only, never the privacy path.

Comparing plaintext sets discloses every identifier to whoever computes. It exists to verify
PSI-CA results against ground truth and is disabled unless DEV_PLAINTEXT_MATCHER=1 everywhere.
"""
from __future__ import annotations


def plaintext_overlap(mine: set[str], theirs: set[str]) -> tuple[int, int, int]:
    """Return (|mine ∩ theirs|, |mine|, |theirs|)."""
    return len(mine & theirs), len(mine), len(theirs)
