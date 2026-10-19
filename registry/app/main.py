"""FederatedKG registry / coordination service (Phase 1: health and public profiles only).

The registry holds identities, channels, requests and audit metadata. It has no mount,
credential or endpoint that can read any agent's private graph.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
AGENT_URLS = {
    pair.split("=", 1)[0]: pair.split("=", 1)[1]
    for pair in os.environ.get("AGENT_HEALTH_URLS", "").split(",") if pair
}
PUBLIC_PROFILES = Path(os.environ.get("PUBLIC_PROFILES", "/app/public/researchers.json"))
BANNER = "Simulated researchers and synthetic knowledge graphs. No real researcher participation."

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
app = FastAPI(title="FederatedKG registry", version="0.1.0")


def _db_ok() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/v1/health")
def health() -> dict:
    return {"service": "registry", "status": "ok" if _db_ok() else "degraded", "database": _db_ok()}


@app.get("/v1/system/health")
async def system_health() -> dict:
    agents = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for agent_id, url in sorted(AGENT_URLS.items()):
            try:
                r = await client.get(url)
                body = r.json()
                # Forward only the fixed, content-free health fields.
                agents[agent_id] = {"status": body.get("status", "unknown"),
                                    "graph_loaded": bool(body.get("graph_loaded"))}
            except Exception:
                agents[agent_id] = {"status": "unreachable", "graph_loaded": False}
    db = _db_ok()
    healthy = db and all(a["status"] == "ok" and a["graph_loaded"] for a in agents.values())
    return {"status": "ok" if healthy else "degraded", "banner": BANNER,
            "registry": {"status": "ok", "database": db}, "agents": agents}


@app.get("/v1/public/personas")
def public_personas() -> dict:
    """Demo-account labels for the login/health page. Authenticated directory arrives in Phase 2."""
    data = json.loads(PUBLIC_PROFILES.read_text(encoding="utf-8"))
    return {
        "banner": BANNER,
        "personas": [
            {k: r[k] for k in ("researcher_id", "display_name", "theme", "verified_researcher",
                               "is_simulated", "public_scientific_inspiration", "disclaimer")}
            for r in data["researchers"]
        ],
    }
