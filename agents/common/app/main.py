"""FederatedKG researcher agent.

Each instance serves exactly one persona's private graph. Internal endpoints require a signed
service token; comparisons additionally require a registry-signed ticket *and* this agent's own
local policy. Private identifiers never leave the agent: PSI-CA exchanges blinded messages only,
and the exact intersection count stays in this agent's own log.
"""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from fkg_protocol.keys import Keyring, load_private
from fkg_protocol.results import shape, sign_package
from fkg_protocol.tickets import counterpart, verify_ticket
from fkg_protocol.tokens import AuthError, ReplayCache, sign_service_token, verify_service_token, wall_now
from similarity.scoped_baseline import plaintext_overlap

from .capture import Capture, CaptureMiddleware
from .config import AgentSettings
from .graph import eligible_sets, graph_metadata, load_private_graph
from .local_policy import AgentState, LocalPolicy

TOKEN_HEADER = "X-Service-Token"
PERSONAS = ("persona_a", "persona_b", "persona_c", "persona_d")
ALGORITHM_VERSION = "fkg-similarity/1.0"
SESSION_TTL_SECONDS = 60

settings = AgentSettings.from_env()
AGENT_ID = settings.agent_id
capture = Capture(settings.capture_file if settings.capture_payloads else None)

# No interactive docs or schema: the agent surface is internal and minimal by design.
app = FastAPI(title=f"FederatedKG agent {AGENT_ID}", version="0.4.0", docs_url=None, redoc_url=None,
              openapi_url=None)
app.add_middleware(CaptureMiddleware, capture=capture)


class Runtime:
    graph = None
    key = None
    keyring = Keyring({})
    policy: LocalPolicy | None = None
    state: AgentState | None = None
    replay = ReplayCache()
    clock_offset = 0.0
    sessions: dict[str, dict] = {}
    lock = threading.Lock()


rt = Runtime()


def now() -> float:
    return wall_now() + rt.clock_offset


@app.on_event("startup")
def _startup() -> None:
    rt.graph = load_private_graph(AGENT_ID, settings.fixture, settings.store_dir)
    rt.key = load_private(settings.private_key)
    rt.keyring = Keyring.from_dir(settings.keyring_dir)
    rt.policy = LocalPolicy.load(settings.local_policy)
    rt.state = AgentState(settings.store_dir / "agent_state.json")


def fail(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


def authenticated(issuers: tuple[str, ...], use_wall_clock: bool = False):
    async def dep(request: Request) -> dict:
        body = await request.body()
        try:
            claims = verify_service_token(request.headers.get(TOKEN_HEADER), rt.keyring, AGENT_ID, request.method,
                                          request.url.path, body, rt.replay,
                                          wall_now() if use_wall_clock else now(), allowed_issuers=issuers)
        except AuthError as e:
            raise fail(401, e.code) from None
        return {"caller": claims["iss"], "body": body}
    return dep


PEERS = tuple(p for p in PERSONAS if p != AGENT_ID)


# ---- outbound calls ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    def on_request(req: httpx.Request):
        capture.write("outbound-request", str(req.url.path), req.content)

    def on_response(resp: httpx.Response):
        resp.read()
        capture.write("inbound-response", str(resp.request.url.path), resp.content)

    return httpx.Client(timeout=30, event_hooks={"request": [on_request], "response": [on_response]})


def signed_call(audience: str, base_url: str, method: str, path: str, payload: dict | None) -> httpx.Response:
    body = json.dumps(payload).encode() if payload is not None else b""
    token = sign_service_token(rt.key, AGENT_ID, audience, method, path, body, now())
    with _client() as c:
        return c.request(method, base_url.rstrip("/") + path, content=body,
                         headers={TOKEN_HEADER: token, "Content-Type": "application/json"})


def registry_ticket_status(ticket_id: str) -> str:
    try:
        r = signed_call("registry", settings.registry_url, "GET", f"/internal/tickets/{ticket_id}", None)
    except httpx.HTTPError:
        return "unreachable"
    return r.json().get("status", "unknown") if r.status_code == 200 else "unknown"


def peer_call(peer: str, path: str, payload: dict) -> dict:
    try:
        r = signed_call(peer, settings.peer_urls[peer], "POST", path, payload)
    except (httpx.HTTPError, KeyError):
        raise fail(502, "peer_unreachable") from None
    if r.status_code != 200:
        try:
            code = r.json()["detail"]["code"]
        except Exception:
            code = f"http_{r.status_code}"
        raise fail(409, f"peer_{code}")
    return r.json()


# ---- shared authorization -----------------------------------------------------------------------

def authorize_ticket(raw_ticket: str) -> dict:
    registry_key = rt.keyring.get("registry")
    if registry_key is None:
        raise fail(503, "registry_key_missing")
    try:
        ticket = verify_ticket(raw_ticket, registry_key, now())
        counterpart(ticket, AGENT_ID)
    except AuthError as e:
        raise fail(403, e.code) from None
    refusal = rt.policy.refusal(ticket, settings.dev_plaintext_matcher)
    if refusal:
        raise fail(403, refusal)
    status = registry_ticket_status(ticket["jti"])
    if status != "active":
        raise fail(409, f"ticket_{status}")
    return ticket


def count_against_limit(ticket: dict) -> None:
    if not rt.state.count_comparison(counterpart(ticket, AGENT_ID), ticket["jti"], now(), rt.policy.pair_daily_limit):
        raise fail(429, "local_pair_limit_reached")


def own_set(cls: str) -> list[str]:
    items = sorted(eligible_sets(rt.graph, [cls])[cls])
    if len(items) < rt.policy.min_eligible_set_size:
        raise fail(422, "local_eligible_set_too_small")
    return items


# ---- client role: the designated output party ----------------------------------------------------

class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str
    consumer_id: str


@app.post("/internal/comparisons/run")
def run_comparison(body: RunBody, request: Request, auth: dict = Depends(authenticated(("registry",)))) -> dict:
    if body.consumer_id != AGENT_ID:
        raise fail(403, "not_the_consumer")
    ticket = authorize_ticket(body.ticket)
    if AGENT_ID not in ticket["result_recipients"]:
        raise fail(403, "not_a_result_recipient")
    if not rt.state.claim(f"{ticket['jti']}:client:{AGENT_ID}"):
        raise fail(409, "ticket_already_used")
    count_against_limit(ticket)
    peer = counterpart(ticket, AGENT_ID)
    scope = ticket["scope"]

    exact: dict[str, dict] = {}
    for cls in scope["entity_classes"]:
        mine = own_set(cls)
        if scope["protocol"] == "psi_ca":
            from similarity.psi_ca import PROTOCOL, PsiCaClient
            client = PsiCaClient(mine)
            setup = peer_call(peer, "/internal/psi/setup", {"ticket": body.ticket, "consumer_id": AGENT_ID,
                                                            "entity_class": cls, "client_size": client.size})
            response = peer_call(peer, "/internal/psi/process", {
                "session_id": setup["session_id"],
                "request": base64.b64encode(client.request_message()).decode()})
            inter = client.cardinality(base64.b64decode(setup["setup"]), base64.b64decode(response["response"]))
            exact[cls] = {"intersection": inter, "own_size": len(mine), "other_size": int(setup["server_size"])}
            method = PROTOCOL
        else:  # plaintext_dev: both agents and the registry must have the dev flag on
            theirs = peer_call(peer, "/internal/plaintext/items", {"ticket": body.ticket, "consumer_id": AGENT_ID,
                                                                    "entity_class": cls})["items"]
            inter, own_size, other_size = plaintext_overlap(set(mine), set(theirs))
            exact[cls] = {"intersection": inter, "own_size": own_size, "other_size": other_size}
            method = "plaintext-dev/scoped-baseline/1"

    delay = float(request.headers.get("X-FKG-Test-Delay", "0") or 0) if settings.test_mode else 0.0
    if delay > 0:
        time.sleep(min(delay, 30))
    # Release gate: a revocation during computation means nothing leaves this agent.
    status = registry_ticket_status(ticket["jti"])
    if status != "active":
        raise fail(409, f"ticket_{status}")

    _log_exact(ticket, peer, method, exact)
    results = {cls: shape(scope["disclosure"], scope["metric"], e["intersection"], e["own_size"], e["other_size"])
               for cls, e in exact.items()}
    package = {
        "request_id": ticket["request_id"], "ticket_id": ticket["jti"], "producer_id": AGENT_ID,
        "consumer_id": AGENT_ID, "counterpart_id": peer, "scope": scope, "policy_version": ticket["policy_version"],
        "method": method, "algorithm_version": ALGORITHM_VERSION,
        "input_provenance": graph_metadata(rt.graph, AGENT_ID),
        "created_at": datetime.fromtimestamp(now(), timezone.utc).isoformat(),
        "results": results,
        "disclosed_to_counterpart": {
            "own_set_size": "exact (inherent to PSI-CA)" if method != "plaintext-dev/scoped-baseline/1"
            else "full plaintext set (development matcher)",
            "intersection": "not revealed to the counterpart",
            "identifiers": "none" if method != "plaintext-dev/scoped-baseline/1" else "all (development matcher)",
        },
    }
    return {"package": sign_package(rt.key, package)}


def _log_exact(ticket: dict, peer: str, method: str, exact: dict) -> None:
    """Exact counts are kept only here, on this agent's own volume."""
    line = {"at": now(), "ticket_id": ticket["jti"], "request_id": ticket["request_id"], "counterpart": peer,
            "method": method, "metric": ticket["scope"]["metric"], "exact": exact}
    with open(settings.store_dir / "comparisons.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


# ---- server role: the non-output party ------------------------------------------------------------

class SetupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str
    consumer_id: str
    entity_class: str
    client_size: int = Field(ge=1)


def _authorize_peer(raw_ticket: str, consumer_id: str, caller: str, entity_class: str) -> dict:
    ticket = authorize_ticket(raw_ticket)
    if caller != counterpart(ticket, AGENT_ID) or consumer_id != caller:
        raise fail(403, "caller_not_ticket_counterpart")
    if consumer_id not in ticket["result_recipients"]:
        raise fail(403, "consumer_not_a_result_recipient")
    if entity_class not in ticket["scope"]["entity_classes"]:
        raise fail(403, "entity_class_not_in_ticket")
    return ticket


@app.post("/internal/psi/setup")
def psi_setup(body: SetupBody, auth: dict = Depends(authenticated(PEERS))) -> dict:
    from similarity.psi_ca import PsiCaServer
    ticket = _authorize_peer(body.ticket, body.consumer_id, auth["caller"], body.entity_class)
    if ticket["scope"]["protocol"] != "psi_ca":
        raise fail(403, "protocol_mismatch")
    if body.client_size > rt.policy.max_counterpart_set_size:
        raise fail(422, "counterpart_set_too_large")
    if not rt.state.claim(f"{ticket['jti']}:server:{body.consumer_id}:{body.entity_class}"):
        raise fail(409, "ticket_already_used")
    count_against_limit(ticket)
    items = own_set(body.entity_class)
    server = PsiCaServer(items)
    session_id = uuid.uuid4().hex
    with rt.lock:
        rt.sessions[session_id] = {"server": server, "caller": auth["caller"], "expires": now() + SESSION_TTL_SECONDS}
    return {"session_id": session_id, "setup": base64.b64encode(server.setup_message(body.client_size)).decode(),
            "server_size": len(items)}


class ProcessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    request: str


@app.post("/internal/psi/process")
def psi_process(body: ProcessBody, auth: dict = Depends(authenticated(PEERS))) -> dict:
    with rt.lock:
        session = rt.sessions.pop(body.session_id, None)  # single use
    if session is None or session["caller"] != auth["caller"] or session["expires"] < now():
        raise fail(404, "psi_session_not_found")
    response = session["server"].process_request(base64.b64decode(body.request))
    return {"response": base64.b64encode(response).decode()}


class ItemsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str
    consumer_id: str
    entity_class: str


@app.post("/internal/plaintext/items")
def plaintext_items(body: ItemsBody, auth: dict = Depends(authenticated(PEERS))) -> dict:
    """Development-only correctness oracle. Discloses identifiers; disabled unless explicitly enabled."""
    if not settings.dev_plaintext_matcher:
        raise fail(403, "plaintext_matcher_disabled")
    ticket = _authorize_peer(body.ticket, body.consumer_id, auth["caller"], body.entity_class)
    if ticket["scope"]["protocol"] != "plaintext_dev":
        raise fail(403, "protocol_mismatch")
    if not rt.state.claim(f"{ticket['jti']}:plaintext:{body.consumer_id}:{body.entity_class}"):
        raise fail(409, "ticket_already_used")
    count_against_limit(ticket)
    return {"items": own_set(body.entity_class)}


# ---- always denied in v1 ----------------------------------------------------------------------------

@app.post("/internal/evidence/export")
def evidence_export(auth: dict = Depends(authenticated(("registry",) + PEERS))) -> dict:
    raise fail(403, "evidence_export_disabled_v1")


# ---- test mode ----------------------------------------------------------------------------------------

class ClockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset_seconds: float = Field(ge=0)


@app.post("/internal/test/clock")
def set_clock(body: ClockBody, auth: dict = Depends(authenticated(("registry",), use_wall_clock=True))) -> dict:
    if not settings.test_mode:
        raise fail(404, "not_found")
    rt.clock_offset = body.offset_seconds
    return {"offset_seconds": rt.clock_offset}


@app.get("/internal/health")
def health() -> dict:
    # Deliberately content-free: no counts, labels or identifiers from the private graph.
    return {"service": "agent", "agent_id": AGENT_ID, "status": "ok",
            "graph_loaded": rt.graph is not None and len(rt.graph) > 0}
