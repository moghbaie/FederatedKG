"""In-process registry tests (SQLite). Row-lock behaviour is covered by live Postgres tests."""
from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from registry.app.clock import Clock
from registry.app.config import Settings
from registry.app.main import create_app
from registry.app.models import Base
from tests.conftest import DATA

PERSONAS = ["persona_a", "persona_b", "persona_c", "persona_d", "persona_e"]
VERIFIED = PERSONAS[:4]


def make_client(tmp_path, test_mode: bool = True, **overrides) -> TestClient:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'registry.db'}", test_mode=test_mode,
                        public_profiles=DATA / "public" / "researchers.json", **overrides)
    app = create_app(settings, Clock(adjustable=test_mode))
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    with make_client(tmp_path) as c:
        yield c


@pytest.fixture
def login(client) -> Callable[[str], dict]:
    def _login(persona: str) -> dict:
        r = client.post("/v1/auth/demo-login", json={"researcher_id": persona})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login


@pytest.fixture
def advance(client) -> Callable[[float], None]:
    def _advance(seconds: float) -> None:
        assert client.post("/v1/test/clock/advance", json={"seconds": seconds}).status_code == 200
    return _advance


@pytest.fixture
def open_channel(client, login) -> Callable[..., dict]:
    def _open(owner: str = "persona_a", topics: list[str] | None = None, activate: bool = True) -> dict:
        h = login(owner)
        ch = client.post("/v1/channels", json={"topics": topics or ["proteomics", "mass_spectrometry"]},
                         headers=h).json()
        if activate:
            ch = client.post(f"/v1/channels/{ch['id']}/activate", headers=h).json()
        return ch
    return _open
