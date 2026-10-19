"""Phase 2 gate: channel lifecycle, owner-only control, topics-only discovery, 24-hour expiry."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from registry.app.models import Channel, ChannelPolicyVersion
from tests.registry.conftest import VERIFIED

DAY = 24 * 3600


def discovered(client, headers) -> list[str]:
    r = client.get("/v1/channels", headers=headers)
    assert r.status_code == 200, r.text
    return [c["id"] for c in r.json()["channels"]]


def code(r) -> str:
    return r.json()["detail"]["code"]


# ---- creation -------------------------------------------------------------------------------

def test_create_draft_uses_token_identity(client, login):
    ch = client.post("/v1/channels", json={"topics": ["proteomics"]}, headers=login("persona_a")).json()
    assert ch["owner_id"] == "persona_a"
    assert ch["status"] == "DRAFT" and ch["policy_version"] == 1 and ch["expires_at"] is None
    assert (ch["audience"], ch["visibility"], ch["approval_mode"]) == ("verified_researchers", "topics", "manual")


def test_client_supplied_owner_is_rejected(client, login):
    r = client.post("/v1/channels", json={"topics": ["proteomics"], "owner_id": "persona_b"},
                    headers=login("persona_a"))
    assert r.status_code == 422


def test_topics_must_be_published_subset(client, login):
    # host_pathogen is persona_d's topic; single_cell_proteomics is persona_a's *private* topic.
    for topics in (["host_pathogen"], ["single_cell_proteomics"]):
        r = client.post("/v1/channels", json={"topics": topics}, headers=login("persona_a"))
        assert r.status_code == 422 and code(r) == "topic_not_published"


# ---- visibility matrix --------------------------------------------------------------------

@pytest.mark.parametrize("viewer,expected", [
    ("persona_a", "hidden"),        # owner: not in discovery, present in /mine
    ("persona_b", "visible"),
    ("persona_c", "visible"),
    ("persona_d", "visible"),
    ("persona_e", "forbidden"),     # unverified
])
def test_visibility_matrix_for_active_channel(client, login, open_channel, viewer, expected):
    ch = open_channel("persona_a")
    h = login(viewer)
    r = client.get("/v1/channels", headers=h)
    if expected == "forbidden":
        assert r.status_code == 403
        assert client.get(f"/v1/channels/{ch['id']}", headers=h).status_code == 403
        return
    ids = [c["id"] for c in r.json()["channels"]]
    assert (ch["id"] in ids) is (expected == "visible")
    if viewer == "persona_a":
        assert ch["id"] in [c["id"] for c in client.get("/v1/channels/mine", headers=h).json()["channels"]]


@pytest.mark.parametrize("state", ["DRAFT", "PAUSED", "CLOSED"])
def test_non_active_channels_are_not_discoverable(client, login, open_channel, state):
    ch = open_channel("persona_a", activate=state != "DRAFT")
    owner = login("persona_a")
    if state == "PAUSED":
        client.post(f"/v1/channels/{ch['id']}/pause", headers=owner)
    if state == "CLOSED":
        client.post(f"/v1/channels/{ch['id']}/close", headers=owner)
    for viewer in ("persona_b", "persona_c", "persona_d"):
        h = login(viewer)
        assert ch["id"] not in discovered(client, h)
        assert client.get(f"/v1/channels/{ch['id']}", headers=h).status_code == 404


def test_discovery_exposes_topics_only_with_topic_match(client, login, open_channel, public_profiles):
    ch = open_channel("persona_a", topics=["proteomics", "mass_spectrometry", "quantitative_proteomics"])
    item = client.get("/v1/channels", headers=login("persona_b")).json()["channels"][0]
    assert set(item) == {"id", "owner", "topics", "visibility", "approval_mode", "expires_at", "topic_match"}
    assert item["owner"] == {"researcher_id": "persona_a", "display_name": "Persona A"}
    b_topics = next(r["published_topics"] for r in public_profiles["researchers"] if r["researcher_id"] == "persona_b")
    inter, union = set(b_topics) & set(ch["topics"]), set(b_topics) | set(ch["topics"])
    assert item["topic_match"]["score"] == round(len(inter) / len(union), 6)
    assert item["topic_match"]["metric"] == "topic_similarity/jaccard"


def test_discovery_ranked_by_topic_match(client, login, open_channel):
    low = open_channel("persona_d", topics=["host_pathogen"])
    high = open_channel("persona_c", topics=["interactomics", "mass_spectrometry"])
    assert discovered(client, login("persona_b")) == [high["id"], low["id"]]


# ---- owner-only control -----------------------------------------------------------------------

@pytest.mark.parametrize("action", ["activate", "pause", "resume", "close"])
@pytest.mark.parametrize("intruder", ["persona_b", "persona_c", "persona_d"])
def test_non_owner_cannot_control_channel(client, login, open_channel, action, intruder):
    ch = open_channel("persona_a", activate=action != "activate")
    r = client.post(f"/v1/channels/{ch['id']}/{action}", headers=login(intruder))
    assert r.status_code == 403 and code(r) == "not_owner"


def test_non_owner_cannot_edit_policy(client, login, open_channel):
    ch = open_channel("persona_a")
    r = client.patch(f"/v1/channels/{ch['id']}", json={"topics": ["proteomics"], "expected_policy_version": 1},
                     headers=login("persona_b"))
    assert r.status_code == 403
    r = client.patch(f"/v1/channels/{ch['id']}", json={"topics": ["proteomics"], "expected_policy_version": 1},
                     headers=login("persona_e"))
    assert r.status_code == 403 and code(r) == "unverified_researcher"


@pytest.mark.parametrize("start,action", [("DRAFT", "pause"), ("DRAFT", "resume"), ("DRAFT", "close"),
                                          ("ACTIVE", "activate"), ("ACTIVE", "resume"),
                                          ("CLOSED", "resume"), ("CLOSED", "activate"), ("CLOSED", "close")])
def test_invalid_transitions(client, login, open_channel, start, action):
    ch = open_channel("persona_a", activate=start != "DRAFT")
    h = login("persona_a")
    if start == "CLOSED":
        client.post(f"/v1/channels/{ch['id']}/close", headers=h)
    r = client.post(f"/v1/channels/{ch['id']}/{action}", headers=h)
    assert r.status_code == 409 and code(r) == "invalid_transition"


# ---- policy versions -------------------------------------------------------------------------

def test_policy_edit_creates_immutable_version_with_optimistic_check(client, login, open_channel):
    ch = open_channel("persona_a", topics=["proteomics", "mass_spectrometry"])
    h = login("persona_a")
    r = client.patch(f"/v1/channels/{ch['id']}", json={"topics": ["proteomics"], "expected_policy_version": 1},
                     headers=h)
    assert r.status_code == 200 and r.json()["policy_version"] == 2 and r.json()["topics"] == ["proteomics"]
    stale = client.patch(f"/v1/channels/{ch['id']}", json={"topics": ["proteomics"], "expected_policy_version": 1},
                         headers=h)
    assert stale.status_code == 409 and code(stale) == "stale_policy_version"
    with client.app.state.sessionmaker() as db:
        versions = db.query(ChannelPolicyVersion).filter_by(channel_id=ch["id"]).order_by("version").all()
    assert [(v.version, v.topics) for v in versions] == [(1, ["mass_spectrometry", "proteomics"]),
                                                        (2, ["proteomics"])]
    item = client.get("/v1/channels", headers=login("persona_b")).json()["channels"][0]
    assert item["topics"] == ["proteomics"]


# ---- 24-hour expiry ---------------------------------------------------------------------------

def test_activation_sets_exact_24h_deadline(client, open_channel):
    ch = open_channel("persona_a")
    activated, expires = (datetime.fromisoformat(ch[k]) for k in ("activated_at", "expires_at"))
    assert expires - activated == timedelta(hours=24)


def test_pause_does_not_extend_expiry(client, login, open_channel, advance):
    ch = open_channel("persona_a")
    h = login("persona_a")
    advance(10 * 3600)
    h = login("persona_a")
    client.post(f"/v1/channels/{ch['id']}/pause", headers=h)
    advance(13 * 3600)
    h = login("persona_a")
    resumed = client.post(f"/v1/channels/{ch['id']}/resume", headers=h).json()
    assert resumed["status"] == "ACTIVE" and resumed["expires_at"] == ch["expires_at"]
    advance(3600 + 1)
    h = login("persona_a")
    mine = client.get("/v1/channels/mine", headers=h).json()["channels"][0]
    assert mine["status"] == "EXPIRED" and mine["expires_at"] == ch["expires_at"]


def test_expired_channel_disappears_and_is_terminal(client, login, open_channel, advance):
    ch = open_channel("persona_a")
    advance(DAY - 1)
    assert ch["id"] in discovered(client, login("persona_b"))
    advance(1)
    assert ch["id"] not in discovered(client, login("persona_b"))
    h = login("persona_a")
    for action in ("pause", "resume", "close"):
        r = client.post(f"/v1/channels/{ch['id']}/{action}", headers=h)
        assert r.status_code == 409 and code(r) == "channel_expired", action
    r = client.patch(f"/v1/channels/{ch['id']}", json={"topics": ["proteomics"], "expected_policy_version": 1},
                     headers=h)
    assert r.status_code == 409 and code(r) == "channel_expired"


def test_paused_channel_cannot_resume_after_expiry(client, login, open_channel, advance):
    ch = open_channel("persona_a")
    client.post(f"/v1/channels/{ch['id']}/pause", headers=login("persona_a"))
    advance(DAY)
    r = client.post(f"/v1/channels/{ch['id']}/resume", headers=login("persona_a"))
    assert r.status_code == 409 and code(r) == "channel_expired"


def test_expiry_enforced_before_status_reconciliation(client, login, open_channel, advance):
    ch = open_channel("persona_a")
    advance(DAY + 5)
    # Single-channel reads do not reconcile: the stored flag is still ACTIVE ...
    r = client.get(f"/v1/channels/{ch['id']}", headers=login("persona_b"))
    with client.app.state.sessionmaker() as db:
        assert db.get(Channel, ch["id"]).status == "ACTIVE"
    # ... yet the channel is already treated as expired.
    assert r.status_code == 404
    owner_view = client.get(f"/v1/channels/{ch['id']}", headers=login("persona_a")).json()
    assert owner_view["status"] == "EXPIRED"


def test_all_verified_accounts_see_identical_eligible_set(client, login, open_channel):
    channels = {p: open_channel(p, topics=None if p != "persona_d" else ["interactomics"])["id"]
                for p in ("persona_a", "persona_d")}
    for viewer in VERIFIED:
        expected = {cid for owner, cid in channels.items() if owner != viewer}
        assert set(discovered(client, login(viewer))) == expected, viewer
