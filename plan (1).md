# FederatedKG MVP Implementation Plan

## 0. Objective and scope

Build a runnable, local web MVP that lets four simulated researcher accounts discover overlap between independently maintained biology knowledge graphs, request a detailed comparison, approve or reject requests, and selectively share evidence. The central registry must never have direct access to private graph stores.

**Core test:** one researcher opens a 24-hour, topic-visible channel for a verified research audience. Three other researchers discover the channel, request similarity comparisons, and receive different outcomes based on explicit manual approvals. Demonstrate targeted one-to-one requests as a second path.

**Important:** The named researchers below are real scientists used as *public research-theme exemplars*. They are not users, endorsers, or participants. All accounts, graph contents not traceable to cited publications, permissions, requests, and messages are synthetic. Label every profile and graph clearly as a demonstration. Do not scrape private or restricted information or impersonate these individuals.

## 1. Four researcher personas

| Simulated account | Public research focus used for seed concepts | Example topics for synthetic KG |
|---|---|---|
| Matthias Mann | Mass spectrometry-based proteomics and quantitative proteomics | mass spectrometry, proteomics, protein abundance, protein interactions |
| John R. Yates III | Proteomics, mass spectrometry, computational analysis of proteins | tandem mass spectrometry, peptide identification, proteomics, interaction evidence |
| Anne-Claude Gingras | Protein interaction networks and affinity purification mass spectrometry | interactomics, AP-MS, protein complexes, interaction networks |
| Nevan Krogan | Protein interaction networks, systems biology, host-pathogen interactions | interactomics, host-pathogen networks, functional genomics, protein complexes |

Before collecting source data, verify each researcher's current public affiliation, research themes, and representative publications against institutional profiles and/or publication metadata. Do not invent citations, findings, or specific collaboration relationships. Store source URL, retrieval date, license/access terms, and publication DOI where available. The four profiles are an MVP fixture, not a claim that any researcher consented to participation.

### Dataset requirements

- Create four isolated RDF graphs, one per simulated account, with 20–30 entities and 30–50 relationships each. Use synthetic data by default, informed by verified public scientific topics.
- Include normalized identifiers for shared concepts (e.g., UniProt accessions for proteins, ontology terms for techniques). Keep a separate mapping from source labels to normalized identifiers.
- Add 3–5 synthetic hypotheses and 5–10 synthetic observations per graph. Include at least one explicitly fabricated contradiction for test purposes.
- Mark every synthetic observation with `is_synthetic=true`; never attribute invented experiments or results to the real researchers.
- Add `source`, `provenance`, `visibility`, `owner`, `created_at`, `confidence`, and `version` fields where applicable.
- Publish only an opt-in subset of topic identifiers in the discovery registry. No private entity list, private edge, observation, or embedding is published by default.
- Seed intentional overlaps and unique areas; save ground-truth overlap sets to verify similarity outputs.

## 2. User journeys

### A. Open channel, one-to-many
1. Simulated Mann account signs in and opens a channel with topics-only visibility, research-audience restriction, manual approval, and 24-hour lifetime.
2. Yates, Gingras, and Krogan accounts discover the public-approved topic listing and see a *topic match* score based solely on published topics.
3. Each sends a request for a detailed similarity comparison with an explicit requested scope and result disclosure level.
4. Mann approves Yates, rejects Gingras, and leaves Krogan pending.
5. Only the approved comparison runs, after both agents independently authorize the inputs and result visibility. Rejected and pending requests reveal no private KG details.
6. Mann tightens a policy. New and pending exports are checked against the new version and denied if incompatible.
7. At 24 hours the channel expires. New requests and unfinished operations are denied or cancelled. Prior authorized disclosures cannot be erased retroactively.

### B. Targeted one-to-one
1. Gingras selects Krogan from the researcher directory and sends a comparison request.
2. Krogan explicitly approves or rejects the requested scope.
3. If approved, both agents calculate an authorized similarity result; a separate agreement is required to share specific evidence.

### C. Open-channel autonomy
- The owner can pause, resume before expiry, close, and restrict their channel unilaterally.
- Any expansion of disclosure requires appropriate bilateral consent.
- The owner can configure result visibility separately from comparison permission.
- Never automatically send contact messages or detailed graph data based on a topic match.

## 3. System architecture

```text
React + TypeScript web app
  | authenticated HTTPS/WebSocket
  v
FastAPI registry / coordination service
  | PostgreSQL (identities, memberships, channels, policy versions,
  | requests, notifications, audit events, authorized result metadata)
  |
  +---- authenticated requests ----> Agent Mann ----> private RDF store Mann
  +---- authenticated requests ----> Agent Yates ---> private RDF store Yates
  +---- authenticated requests ----> Agent Gingras -> private RDF store Gingras
  +---- authenticated requests ----> Agent Krogan --> private RDF store Krogan

Detailed comparisons: authenticated agent-to-agent protocol or encrypted relay;
registry does not read or mount private RDF stores.
```

For local development, Docker Compose runs one registry, one PostgreSQL database, four agent containers, and one frontend. Each agent has a separate volume and separate credentials. Docker isolation is a functional simulation, not a substitute for separate institutional security boundaries.

### Recommended stack
- Frontend: React, TypeScript, Vite, TanStack Query, Cytoscape.js (optional graph explorer), Playwright.
- Registry: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, httpx.
- Agents: Python, FastAPI, RDFLib, NetworkX, scikit-learn.
- Authentication: OIDC in later deployments; for local MVP use a test identity provider or clearly labeled demo login with server-issued short-lived tokens. Never trust client-provided owner IDs.
- Signing: `cryptography` Ed25519 for evidence package signatures; TLS for transport, with service authentication.
- Testing: pytest, pytest-asyncio, Hypothesis, Playwright.
- No blockchain, LLM agents, Bluetooth, or private set intersection in MVP v1.

## 4. Repository layout

```text
federatedkg/
  plan.md
  README.md
  compose.yaml
  .env.example
  frontend/
    src/pages/{Dashboard,Directory,Channels,Requests,Matches,Audit}.tsx
    src/components/
    tests/e2e/
  services/
    registry/
      app/{api,auth,models,schemas,services,policies,db}/
      migrations/
    agent/
      app/{api,graph,similarity,policy,exchange,provenance}/
  packages/
    protocol/                # shared Pydantic request/response schemas
  fixtures/
    researchers.json
    graphs/{mann,yates,gingras,krogan}.ttl
    sources.csv
    ground_truth.json
  tests/{unit,integration,security}/
  scripts/{seed,reset_demo,run_e2e}.py
```

## 5. Data contracts

### Discovery channel
Fields: `id`, `owner_id`, `topics` (controlled identifiers), `audience=verified_researchers`, `visibility=topics`, `approval_mode=manual`, `status`, `activated_at`, `expires_at`, `policy_version`, `created_at`.

On activation set `expires_at = activated_at + 24 hours` in UTC. Pause does not extend expiration. Every read and authorization checks wall-clock expiration, not only a background job's status flag.

### Comparison request
Fields: `id`, `channel_id` or `target_researcher_id`, `requester_id`, `recipient_id`, `requested_scope`, `result_visibility`, `status`, `created_at`, `decision_at`, `approved_policy_version`, `expires_at`, `idempotency_key`.

### Evidence/result package
Fields: `request_id`, `producer_id`, `consumer_id`, `scope`, `policy_version`, `method`, `algorithm_version`, `input_provenance`, `created_at`, `expires_at`, `result`, `signature`. Only explicitly authorized fields may appear in the returned package.

### Audit event
Fields: `id`, `actor_id`, `action`, `object_type`, `object_id`, `timestamp`, `policy_version`, `decision`, `reason_code`, `correlation_id`. Audit records should not contain secret graph payloads.

## 6. State machines

Channel: `DRAFT -> ACTIVE -> PAUSED -> ACTIVE` (if not expired); `ACTIVE|PAUSED -> CLOSED`; expiration is terminal and enforced even before status reconciliation. Only owner may modify or close.

Request: `PENDING -> APPROVED|REJECTED|CANCELLED|EXPIRED`; `APPROVED -> RUNNING -> COMPLETED|FAILED|CANCELLED|EXPIRED`. Policy changes can invalidate approval before result release. All transitions are validated server-side and recorded transactionally.

## 7. REST API endpoints

### Registry
- `POST /v1/channels`: create draft channel for authenticated owner.
- `POST /v1/channels/{id}/activate`: activate and start 24-hour timer.
- `GET /v1/channels`: list eligible topic-visible channels.
- `PATCH /v1/channels/{id}`: owner updates allowed settings, creating immutable policy version.
- `POST /v1/channels/{id}/pause`, `/resume`, `/close`: owner controls.
- `POST /v1/channels/{id}/requests`: verified member submits scoped comparison request.
- `POST /v1/researchers/{id}/requests`: targeted one-to-one comparison request.
- `GET /v1/requests/inbox`: pending requests for authenticated recipient.
- `POST /v1/requests/{id}/approve`, `/reject`, `/cancel`: authorized transitions.
- `GET /v1/requests/{id}/result`: result visible only to authorized actors and permitted disclosure level.
- `GET /v1/audit`: actor-scoped audit events.
- `GET /v1/me`, `GET /v1/researchers`: own profile and authorized researcher directory.

### Agent
- `POST /internal/similarity/prepare`: validate signed request, requester, scope, policy version, expiry.
- `POST /internal/similarity/execute`: compute only approved comparison representation.
- `POST /internal/evidence/export`: deny unless separate evidence-sharing agreement permits it.
- `GET /internal/health`: health check without private graph content.

Require authenticated service identity for internal endpoints. Do not expose agent endpoints directly to arbitrary browsers.

## 8. Similarity algorithm

**Stage 1: discovery ranking.** Compute Jaccard or weighted overlap on *published topic identifiers only*. Label the output `topic_similarity`, not `knowledge_graph_similarity`. Use deterministic scores with fixture ground truth. Show the matched published topics only when allowed.

**Stage 2: approved detailed comparison.** For v1, compare narrowly scoped, explicitly approved normalized entity/relationship sets. Use Jaccard entity overlap and normalized triple overlap, plus separate `contradiction_count` on synthetic evidence. Do not combine contradiction and agreement into one opaque score. Track algorithm version and input provenance.

**Security caveat:** Plain entity-set transfer is not private set intersection. It discloses those authorized identifiers to the receiver. Do not claim cryptographic privacy. Defer PSI/PSI-cardinality to a future research milestone. Rate-limit repeated comparisons to reduce probing and inference attacks.

## 9. Web application screens

1. **Researcher selector / demo login:** four clearly labeled simulated accounts; four separate browser contexts in E2E tests.
2. **My KG:** local-only graph visualization with public/private node indicators.
3. **Directory:** searchable profiles and one-to-one request action.
4. **Discover:** topic-visible open channels and topic match scores.
5. **My Channels:** create, activate, pause, resume, close, policy edit, 24-hour countdown.
6. **Requests Inbox:** approve, reject, see requested scope and disclosure level.
7. **Matches:** authorized similarity breakdown, status, and optional contact request.
8. **Audit:** policy versions, decisions, comparison events, and revocations.

Provide a reset-demo button that reseeds deterministic fixtures. Show a persistent banner: `Simulated researchers and synthetic knowledge graphs. No real researcher participation.`

## 10. Permission enforcement requirements

- Deny by default. Verify identity, verified research membership, owner, channel audience, scope, policy version, request state, expiration, and result visibility on every protected operation.
- Use database transactions and row locks for approvals and policy updates; use optimistic version checks to avoid stale changes.
- A researcher can restrict their own disclosures immediately. A broader agreement cannot override a narrower local policy.
- Policy edits create immutable versions; approved-but-not-completed requests must be revalidated at execution and release.
- Approval to compare does not authorize sharing graph triples or raw observations.
- Protect against replay with signed request IDs, timestamps, nonce/idempotency keys, and expiry.
- Apply request rate limits and privacy budgets/thresholds as needed; do not expose sensitive low-count overlaps by default.
- Never log graph secrets, tokens, or raw evidence payloads.
- Ensure the registry has no filesystem mount, DB credentials, or administrative endpoint that can read any agent's private graph.

## 11. Build phases and acceptance gates

### Phase 1: Repository, Docker, fixtures
- Scaffold monorepo, CI, compose, registry and four agents, private volumes, synthetic RDF fixtures.
- Verify public research themes and source references before populating persona descriptions.
- **Gate:** all services healthy; registry cannot directly read any private graph; deterministic fixture tests pass.

### Phase 2: Identity, audience, channel registry
- Implement demo identities, verified research membership, CRUD, topics-only discovery, 24-hour expiry.
- **Gate:** all four accounts see only eligible channels; unverified account denied; expiration tested with a controllable clock.

### Phase 3: Requests and manual approvals
- Implement targeted and open-channel requests, inbox, state machine, notifications, versioned policies.
- **Gate:** owner can approve/reject; non-owner cannot; policy tightening blocks subsequent unauthorized operations.

### Phase 4: Similarity engine
- Implement topic Jaccard and approved entity/triple comparisons, provenance and contradiction reporting.
- **Gate:** exact expected scores from fixture ground truth; rejected requests return no detailed result.

### Phase 5: React UI
- Build all eight screens with responsive design, status feedback, privacy warnings, audit timeline.
- **Gate:** user can complete full workflow without using curl or database admin tools.

### Phase 6: Automated four-researcher test
- Use Playwright with four isolated browser contexts and separate credentials.
- Run A opens channel; B/C/D request; A approves B, rejects C, leaves D pending; B receives result, C/D do not.
- A pauses channel and then tightens policy; verify new requests blocked and stale approvals invalidated.
- Advance test clock by 24 hours; verify channel expiry and cancellation of incomplete work.
- Run targeted Gingras-to-Krogan flow with manual approval.
- **Gate:** end-to-end and security tests pass with repeatable output and no cross-account leakage.

### Phase 7: Documentation and demo
- README with setup, commands, architecture, threat model, synthetic-data statement, known limitations.
- Include screenshot walkthrough, test report, and reproducible demo script.
- **Gate:** a fresh machine can run `docker compose up --build`, seed fixtures, open the UI, and execute tests using documented commands.

## 12. Mandatory test cases

- Topic-only discovery never leaks private entities, triples, observations, or private embeddings.
- Unverified or non-member requester cannot view restricted channels or submit requests.
- Unauthorized user cannot approve another owner's requests or edit their policy.
- Manual approval is required before detailed comparison.
- Reject, pending, cancelled, and expired requests cannot return detailed results.
- Approval expires or is invalidated on incompatible policy change.
- Race test: policy revocation during computation prevents result release.
- Repeated/duplicate requests are idempotent and rate-limited.
- A graph store cannot be queried through the registry API or another researcher's ordinary browser session.
- No real scientist is represented as an active participant; all demonstration activity is clearly synthetic.

## 13. Out of scope for v1

Real account onboarding for named scientists, live publication scraping, automated messaging to real people, LLM inference, federated learning, private set intersection, blockchain, Bluetooth, Wi-Fi Direct, fully automatic evidence propagation, and production-grade institutional SSO.

## 14. Definition of done

The local web app runs with four independently isolated simulated researcher accounts. A can open a 24-hour, research-audience, topics-only discovery channel; B, C, and D can discover it and submit requests; A can approve, reject, or leave requests pending; detailed similarity is shown only to authorized parties; owner-controlled policy changes and expiry take effect; targeted one-to-one discovery works; provenance and audit are visible; and automated browser/API/security tests pass.

## 15. First implementation command for a coding agent

Implement Phase 1 only. Create the repository skeleton, Docker Compose services, four synthetic RDF graph fixtures, seeded researcher profiles with clear non-endorsement labels, and a health-check page. Do not implement private comparison or policy logic until isolation tests pass. Then proceed phase by phase, stopping at each acceptance gate and reporting test results.
