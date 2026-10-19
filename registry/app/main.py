"""FederatedKG registry / coordination service.

The registry holds identities, channels, requests and audit metadata. It has no mount,
credential or endpoint that can read any agent's private graph.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from . import channels, identity, testing
from .clock import Clock
from .config import Settings
from .deps import get_settings

BANNER = "Simulated researchers and synthetic knowledge graphs. No real researcher participation."


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    Session = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with Session() as db:
            identity.seed_researchers(db, settings)
        yield
        engine.dispose()

    app = FastAPI(title="FederatedKG registry", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock or Clock(adjustable=settings.test_mode)
    app.state.engine = engine
    app.state.sessionmaker = Session

    def db_ok() -> bool:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @app.get("/v1/health")
    def health() -> dict:
        ok = db_ok()
        return {"service": "registry", "status": "ok" if ok else "degraded", "database": ok,
                "test_mode": settings.test_mode}

    @app.get("/v1/system/health")
    async def system_health(s: Settings = Depends(get_settings)) -> dict:
        agents = {}
        async with httpx.AsyncClient(timeout=3.0) as client:
            for agent_id, url in sorted(s.agent_health_urls.items()):
                try:
                    body = (await client.get(url)).json()
                    # Forward only the fixed, content-free health fields.
                    agents[agent_id] = {"status": body.get("status", "unknown"),
                                        "graph_loaded": bool(body.get("graph_loaded"))}
                except Exception:
                    agents[agent_id] = {"status": "unreachable", "graph_loaded": False}
        db = db_ok()
        healthy = db and all(a["status"] == "ok" and a["graph_loaded"] for a in agents.values())
        return {"status": "ok" if healthy else "degraded", "banner": BANNER,
                "registry": {"status": "ok", "database": db}, "agents": agents}

    @app.get("/v1/public/personas")
    def public_personas(s: Settings = Depends(get_settings)) -> dict:
        """Demo-account labels for the sign-in page (public, non-sensitive)."""
        data = json.loads(s.public_profiles.read_text(encoding="utf-8"))
        return {"banner": BANNER, "personas": [
            {k: r[k] for k in ("researcher_id", "display_name", "theme", "verified_researcher",
                               "is_simulated", "public_scientific_inspiration", "disclaimer")}
            for r in data["researchers"]]}

    app.include_router(identity.router)
    app.include_router(channels.router)
    if settings.test_mode:
        app.include_router(testing.router)
    return app


def app_factory() -> FastAPI:
    return create_app()
