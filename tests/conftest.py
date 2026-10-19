from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic"
GRAPH_PERSONAS = ["persona_a", "persona_b", "persona_c", "persona_d"]
AGENT_SERVICES = {"persona_a": "agent_a", "persona_b": "agent_b", "persona_c": "agent_c", "persona_d": "agent_d"}
BASE_URL = os.environ.get("FKG_BASE_URL", "http://localhost:8080")


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=check)


@pytest.fixture(scope="session")
def ground_truth() -> dict:
    return json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def public_profiles() -> dict:
    return json.loads((DATA / "public" / "researchers.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def compose_config() -> dict:
    return json.loads(compose("config", "--format", "json").stdout)


@pytest.fixture(scope="session")
def live_stack() -> str:
    """Live tests are opt-in (-m live); once selected, an unreachable stack is a failure, not a skip."""
    try:
        httpx.get(f"{BASE_URL}/api/v1/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"stack not reachable at {BASE_URL}; run `docker compose up -d --wait` first ({exc})")
    return BASE_URL
