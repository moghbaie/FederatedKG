from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _flag(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes"}


def _mapping(raw: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in (p.split("=", 1) for p in raw.split(",") if p.strip())}


@dataclass(frozen=True)
class AgentSettings:
    agent_id: str
    fixture: Path = Path("/fixtures/graph.ttl")
    store_dir: Path = Path("/var/lib/fkg")
    private_key: Path = Path("/keys/private/private.pem")
    keyring_dir: Path = Path("/keys/public")
    local_policy: Path = Path("/config/policy.json")
    registry_url: str = "http://registry:8000"
    peer_urls: dict[str, str] = field(default_factory=dict)
    test_mode: bool = False
    # Test-only: record every inbound/outbound payload for the leak scan.
    capture_payloads: bool = False
    capture_file: Path = Path("/tmp/fkg-capture/payloads.log")
    # Development-only plaintext matcher (correctness oracle). Never the privacy path.
    dev_plaintext_matcher: bool = False

    @classmethod
    def from_env(cls) -> "AgentSettings":
        env = os.environ
        return cls(
            agent_id=env["AGENT_ID"],
            fixture=Path(env.get("GRAPH_FIXTURE", "/fixtures/graph.ttl")),
            store_dir=Path(env.get("STORE_DIR", "/var/lib/fkg")),
            private_key=Path(env.get("SERVICE_PRIVATE_KEY", "/keys/private/private.pem")),
            keyring_dir=Path(env.get("SERVICE_KEYRING_DIR", "/keys/public")),
            local_policy=Path(env.get("LOCAL_POLICY", "/config/policy.json")),
            registry_url=env.get("REGISTRY_URL", "http://registry:8000"),
            peer_urls=_mapping(env.get("PEER_URLS", "")),
            test_mode=_flag("FKG_TEST_MODE"),
            capture_payloads=_flag("FKG_CAPTURE_PAYLOADS"),
            dev_plaintext_matcher=_flag("DEV_PLAINTEXT_MATCHER"),
        )
