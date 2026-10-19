"""Reset the running demo: wipe channels and audit, reseed public profiles, reset the test clock.

Requires the stack to run with FKG_TEST_MODE=1. Usage: uv run python scripts/reset_demo.py [base_url]
"""
from __future__ import annotations

import sys

import httpx

base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
r = httpx.post(f"{base}/api/v1/test/reset", timeout=10)
if r.status_code == 404:
    sys.exit("reset unavailable: the registry is not running in test mode (FKG_TEST_MODE=1)")
r.raise_for_status()
print("demo reset:", r.json())
