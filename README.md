# FederatedKG (MVP, Phase 3)

> **Simulated researchers and synthetic knowledge graphs. No real researcher participation.**
> Personas A–D cite published work by real scientists *only* as public research-theme inspiration.
> Those scientists are not users, participants or endorsers. Every graph, hypothesis and observation is synthetic.

FederatedKG lets researcher agents discover topic overlap through a central registry and, after
manual approval, compare private knowledge graphs using PSI-CA (private set intersection
cardinality) without exchanging plaintext entity lists. See [plan.md](plan.md) for the full plan.

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Skeleton, isolated services, synthetic fixtures, health page, PSI-CA library check | done |
| 2 | Demo identities (A–E), verified membership, channels, 24-hour expiry, topic discovery | done |
| 3 | Comparison requests, manual approvals, versioned policy enforcement, quotas, audit | done |
| 4 | Signed tickets, agent-to-agent PSI-CA, result release | next |

## Registry API

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /v1/auth/demo-login` | anyone | Demo sign-in for a simulated account. Returns a 30-minute signed token. Stands in for OIDC. |
| `GET /v1/me` | any signed-in account | Own public profile |
| `GET /v1/researchers` | verified | Directory of other verified researchers, ranked by topic match |
| `POST /v1/channels` | verified | Create a draft channel. Topics must be a subset of the owner's published topics. |
| `POST /v1/channels/{id}/activate`, `pause`, `resume`, `close` | owner | Lifecycle controls. Activation starts the 24-hour countdown, and pausing doesn't extend it. |
| `PATCH /v1/channels/{id}` | owner | Edit topics. Requires `expected_policy_version` and creates a new, unchangeable policy version. |
| `GET /v1/channels` | verified | Other researchers' active, unexpired channels: topics plus `topic_similarity`, nothing else |
| `GET /v1/channels/mine`, `GET /v1/channels/{id}` | owner / verified | Own channels; a single channel (non-owners see only discoverable channels) |
| `GET /v1/channels/{id}/policy-versions` | owner | Full history of the channel's policy versions |
| `POST /v1/channels/{id}/requests` | verified | Request a comparison through an open channel |
| `POST /v1/researchers/{id}/requests` | verified | One-to-one comparison request |
| `GET /v1/requests/inbox`, `GET /v1/requests/outbox` | verified | Requests you've received; requests you've sent |
| `GET /v1/requests/{id}` | the two parties | Status, scope, and `execution_check` once approved |
| `POST /v1/requests/{id}/approve`, `reject` | recipient | Manual decision, checked against the current policy |
| `POST /v1/requests/{id}/cancel` | requester | Withdraw a pending or approved request |
| `GET /v1/requests/{id}/result` | parties permitted by `result_visibility` | Arrives in Phase 4. Never available for requests that aren't completed. |
| `GET /v1/notifications` | signed in | In-app notices about requests |
| `GET /v1/audit` | signed in | Your actions, plus events on your channels and on requests you're party to |

How the rules are enforced:
- **Identity** comes only from the token. A request body that tries to set `owner_id` is rejected.
- **Persona E** (unverified) can sign in and read `/v1/me`. Everything else returns 403, and each denial is logged in the audit trail.
- **Expiry** is computed from `expires_at` against the registry clock on every read and action. It doesn't depend on a background job having updated the stored status.

**The request scope contract.** Each request specifies:

```json
{"scope": {"topics": ["interactomics"], "entity_classes": ["Protein"], "metric": "jaccard",
           "protocol": "psi_ca", "disclosure": "score_only", "normalization": "fkg-norm/1.0"},
 "result_visibility": "requester_only", "idempotency_key": "<client-generated>"}
```

Validation rules:
- Scope topics must come from the channel's topics. For one-to-one requests, they must come from the recipient's published topics.
- `evidence` disclosure is always refused in v1.
- `plaintext_dev` is accepted only when `DEV_PLAINTEXT_MATCHER=1`.

What enforcement looks like:
- **Policy edits:** editing a policy re-checks every open request on that channel in the same database transaction. Requests that no longer fit are cancelled with `policy_incompatible`.
- **Closing a channel** cancels its unfinished requests.
- **Expiry:** when a channel or request expires, its open requests expire with it.
- **Duplicates and replays:**
  - Reusing an idempotency key returns the original request.
  - A second open request with an identical scope is refused.
- **Quotas:** each requester–recipient pair is limited to 5 requests and 3 distinct scopes per rolling 24 hours. Every refusal is audited.
- **Concurrency:** approvals, policy edits, closures and submissions take database row locks in a fixed order (channel, then request) and are race-tested against Postgres.

**Test mode** (`FKG_TEST_MODE=1`, the default for the local stack) adds three endpoints:
- `GET /v1/test/clock`
- `POST /v1/test/clock/advance`
- `POST /v1/test/reset`, also available as `uv run python scripts/reset_demo.py`

Turn test mode off anywhere other than a local demo.

## Run

Requirements: Docker Desktop or Engine with Compose v2, [uv](https://docs.astral.sh/uv/), and Node 22 (frontend development only).

```sh
docker compose up -d --build --wait      # registry, postgres, 4 agents, frontend
open http://localhost:8080               # health page and simulated accounts
uv sync
uv run pytest                            # unit and static security tests (no stack needed)
uv run pytest -m live                    # live isolation, health and PSI-CA smoke tests
docker compose down -v                   # stop and wipe volumes
```

To regenerate the fixtures after editing `scripts/fixture_spec.py`, run `uv run python scripts/build_fixtures.py`. CI fails if the committed fixtures are stale.

## Layout

| Path | Contents |
|---|---|
| `registry/` | FastAPI coordination service. It has no volumes and no route to private graphs. |
| `agents/common/` | The single agent image. `agents/persona_*` hold per-persona configuration only. |
| `similarity/` | `public_topics` (Stage 1), `scoped_baseline` (plaintext-dev oracle, Phase 4a), `psi_ca` (OpenMined PSI 2.0.6). |
| `data/synthetic/public/` | Public discovery profiles and source records. The registry image contains only these. |
| `data/synthetic/private/` | One graph and ID mapping per persona. Each is bind-mounted read-only into its own agent only. |
| `data/synthetic/ground_truth.json` | Test-only expected values. Excluded from every image build context. |

## Isolation model (local)

Four Docker networks separate the services:

| Network | Connects |
|---|---|
| `edge` | frontend and registry |
| `data` | registry and postgres (internal) |
| `agents` | registry and agents (internal) |
| `peer` | agent to agent (internal; the registry is not attached) |

- Only the frontend publishes a host port.
- Agents expose `/internal/health` and nothing else. Their health response has no counts or identifiers.
- Each graph contains a unique canary entity. Tests check that no canary appears in the registry container or in another persona's agent.

Docker isolation simulates institutional boundaries and does not replace them. Deployment needs HTTPS and mTLS, or an equivalent service identity.

## Data provenance

- Protein identifiers are UniProtKB accessions. All were verified as reviewed entries on 2026-10-19; UniProt data is licensed CC BY 4.0.
- Method identifiers are PSI-MI terms, verified through EBI OLS4.
- Topics use a local vocabulary, `urn:fkg:topic:*`.
- Citations were checked through Crossref. See `data/synthetic/public/sources.csv`.

## Known limitations (so far)

- The test-clock offset is held in the registry process, which assumes a single registry worker (the default).
- Unless `REGISTRY_TOKEN_SECRET` is set, the token key is random per start, so a restart signs everyone out.
- PSI-CA is integrated only as a library smoke test. Agent-to-agent PSI-CA, tickets and service tokens come in Phase 4.
- PSI-CA reveals the exact intersection size to the output party and each set's size to the other party. Coarse bands will be a display policy, not a cryptographic guarantee. The integration is semi-honest and has not been reviewed.
- The Postgres password in `.env.example` and the defaults are for development only.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE), which also covers third-party data attribution.
