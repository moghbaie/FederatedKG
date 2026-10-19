# API reference

All browser-facing endpoints are served by the registry under `/api` through the frontend (for example,
`http://localhost:8080/api/v1/me`). Authenticate with `Authorization: Bearer <token>` from the demo login.
Errors return `{"detail": {"code": "...", "message": "..."}}`.

## Registry: identity and directory

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /v1/auth/demo-login` `{researcher_id}` | anyone | Labelled demo sign-in. Returns a 30-minute EdDSA-signed token (stands in for OIDC). |
| `GET /v1/me` | any signed-in account | Own public profile |
| `GET /v1/researchers` | verified | Other verified researchers, ranked by published-topic match |
| `GET /v1/public/personas`, `GET /v1/health`, `GET /v1/system/health` | anyone | Sign-in page data and health checks (no graph content) |

## Registry: channels

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /v1/channels` `{topics, max_disclosure?, allowed_result_visibility?}` | verified | Create a draft. Topics must be a subset of your published topics. |
| `POST /v1/channels/{id}/activate`, `pause`, `resume`, `close` | owner | Lifecycle. Activation sets a 24-hour deadline. Pausing doesn't extend it. Closing cancels unfinished requests. |
| `PATCH /v1/channels/{id}` `{expected_policy_version, topics?, max_disclosure?, allowed_result_visibility?}` | owner | Creates a new, unchangeable policy version and re-checks open requests in the same transaction |
| `GET /v1/channels` | verified | Discover: other researchers' active channels, showing topics and `topic_similarity` only |
| `GET /v1/channels/mine`, `GET /v1/channels/{id}`, `GET /v1/channels/{id}/policy-versions` | owner / verified | Own channels; a single channel (non-owners see only discoverable channels); version history |

## Registry: requests, runs and results

```json
{"scope": {"topics": ["interactomics"], "entity_classes": ["Protein", "Interaction"], "metric": "jaccard",
           "protocol": "psi_ca", "disclosure": "summary", "normalization": "fkg-norm/1.0"},
 "result_visibility": "both", "idempotency_key": "<client-generated>"}
```

| Endpoint | Who | Purpose |
|---|---|---|
| `POST /v1/channels/{id}/requests` | verified | Request a comparison through an open channel |
| `POST /v1/researchers/{id}/requests` | verified | One-to-one request. Lapses after 72 hours. |
| `GET /v1/requests/inbox`, `GET /v1/requests/outbox`, `GET /v1/requests/{id}` | the two parties | Status, scope, and `execution_check` once approved |
| `POST /v1/requests/{id}/approve`, `reject` | recipient | Manual decision, checked against the current policy |
| `POST /v1/requests/{id}/cancel` | requester | Withdraw a pending or approved request |
| `POST /v1/requests/{id}/run` | requester | Issue a ticket and dispatch to the agents. Returns 202; poll the request. |
| `GET /v1/requests/{id}/result` | parties permitted by `result_visibility` | Your own signed package: bands, set-size buckets (summary), method, provenance, what the other side learned |
| `POST /v1/requests/{id}/contact` | either party, after COMPLETED | Manual, in-app-only contact notice |
| `GET /v1/notifications`, `POST /v1/notifications/{id}/read` | signed in | In-app notifications |
| `GET /v1/audit` | signed in | Your actions, plus events on your channels and on requests you're party to |

Validation rules:
- `evidence` disclosure is always refused in v1.
- `plaintext_dev` is accepted only with `DEV_PLAINTEXT_MATCHER=1`.
- Per pair of researchers: at most 5 requests and 3 distinct scopes per rolling 24 hours.
- A second open request with an identical scope is refused.

## Registry: test mode only (`FKG_TEST_MODE=1`)

| Endpoint | Purpose |
|---|---|
| `GET /v1/test/clock`, `POST /v1/test/clock/advance` `{seconds}` | Registry clock. Advances are pushed to the agents with a signed call. |
| `POST /v1/test/agent-delay` `{seconds}` | Widen the compute-to-release window, for race tests |
| `POST /v1/test/reset` | Wipe channels, requests, tickets, results, audit and notifications; reseed profiles; reset the clock and each agent's local state |

Every response carries an `X-Registry-Now` header so the UI can show countdowns on the registry clock.

## Internal (service-authenticated, not exposed to browsers)

Every call carries `X-Service-Token`: an EdDSA token bound to caller, audience, method, path and body hash, valid for
60 seconds and never accepted twice.

| Endpoint | Caller → callee | Purpose |
|---|---|---|
| `POST /internal/comparisons/run` | registry → output agent | Run the ticketed comparison and return a signed package |
| `POST /internal/psi/setup`, `/internal/psi/process` | agent → peer agent | PSI-CA messages (blinded) |
| `POST /internal/plaintext/items` | agent → peer agent | Development oracle only; returns 403 unless enabled |
| `GET /internal/tickets/{jti}` | agent → registry | Is the ticket still active? |
| `POST /internal/evidence/export` | any service | Always 403 in v1 |
| `POST /internal/test/clock`, `/internal/test/reset` | registry → agents | Test mode only |
| `GET /owner/graph` | owner's browser → own agent (via `/agent/<persona>/owner/graph`) | My KG. The registry-signed user token's subject must equal the agent's persona. |
| `GET /internal/health` | anyone on the network | Content-free health check |
