from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


def _mapping(raw: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in (p.split("=", 1) for p in raw.split(",") if p.strip())}


@dataclass(frozen=True)
class Settings:
    database_url: str
    # No default secret: when unset, a random per-process key is used (tokens die on restart).
    token_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    token_ttl_seconds: int = 30 * 60
    channel_lifetime_seconds: int = 24 * 60 * 60
    # Targeted (one-to-one) requests and their approvals lapse after this long.
    targeted_request_ttl_seconds: int = 72 * 60 * 60
    # Anti-probing limits per (requester, recipient) pair over a rolling 24 hours.
    pair_request_limit: int = 5
    pair_distinct_scope_limit: int = 3
    # Accept protocol="plaintext_dev" (correctness oracle only; never the privacy path).
    dev_plaintext_matcher: bool = False
    # Enables the controllable clock and reset endpoints. Never enable outside local demo/tests.
    test_mode: bool = False
    public_profiles: Path = Path("/app/public/researchers.json")
    # Agent base URLs by persona id (registry reaches them on the internal `agents` network).
    agent_urls: dict[str, str] = field(default_factory=dict)
    # Ed25519 identity: own private key (ticket + service-token signing) and the public keyring.
    private_key_path: Path | None = None
    keyring_dir: Path | None = None

    @property
    def agent_health_urls(self) -> dict[str, str]:
        return {k: f"{v.rstrip('/')}/internal/health" for k, v in self.agent_urls.items()}

    @classmethod
    def from_env(cls) -> "Settings":
        kwargs = {}
        if os.environ.get("REGISTRY_TOKEN_SECRET"):
            kwargs["token_secret"] = os.environ["REGISTRY_TOKEN_SECRET"]
        if os.environ.get("SERVICE_PRIVATE_KEY"):
            kwargs["private_key_path"] = Path(os.environ["SERVICE_PRIVATE_KEY"])
        if os.environ.get("SERVICE_KEYRING_DIR"):
            kwargs["keyring_dir"] = Path(os.environ["SERVICE_KEYRING_DIR"])
        return cls(
            database_url=os.environ["DATABASE_URL"],
            test_mode=_flag("FKG_TEST_MODE"),
            dev_plaintext_matcher=_flag("DEV_PLAINTEXT_MATCHER"),
            public_profiles=Path(os.environ.get("PUBLIC_PROFILES", "/app/public/researchers.json")),
            agent_urls=_mapping(os.environ.get("AGENT_URLS", "")),
            **kwargs,
        )
