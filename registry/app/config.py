from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    # No default secret: when unset, a random per-process key is used (tokens die on restart).
    token_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    token_ttl_seconds: int = 30 * 60
    channel_lifetime_seconds: int = 24 * 60 * 60
    # Enables the controllable clock and reset endpoints. Never enable outside local demo/tests.
    test_mode: bool = False
    public_profiles: Path = Path("/app/public/researchers.json")
    agent_health_urls: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        agents = dict(pair.split("=", 1) for pair in os.environ.get("AGENT_HEALTH_URLS", "").split(",") if pair)
        kwargs = {}
        if os.environ.get("REGISTRY_TOKEN_SECRET"):
            kwargs["token_secret"] = os.environ["REGISTRY_TOKEN_SECRET"]
        return cls(
            database_url=os.environ["DATABASE_URL"],
            test_mode=_flag("FKG_TEST_MODE"),
            public_profiles=Path(os.environ.get("PUBLIC_PROFILES", "/app/public/researchers.json")),
            agent_health_urls={k.strip(): v.strip() for k, v in agents.items()},
            **kwargs,
        )
