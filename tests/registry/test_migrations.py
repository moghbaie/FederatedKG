"""The Alembic migration chain must produce exactly the schema the models declare."""
from __future__ import annotations

import sys

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from tests.conftest import ROOT


def test_migrations_match_models(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    # migrations/env.py imports `app.models` as it does inside the registry container.
    monkeypatch.syspath_prepend(str(ROOT / "registry"))
    cfg = Config(str(ROOT / "registry" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "registry" / "migrations"))
    command.upgrade(cfg, "head")

    from app.models import Base  # noqa: PLC0415 - resolved via the prepended path

    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    sys.modules.pop("app.models", None)
    assert diff == [], diff
