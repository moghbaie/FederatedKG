# FederatedKG MVP Implementation Plan (v2, consolidated)

Supersedes `plan (1).md`. Incorporates the final decisions on the 11 open questions and the
PSI-CA revision of Stage 2. Where this file and `plan (1).md` disagree, this file wins.

## 0. Objective

A runnable local web MVP in which simulated researcher accounts discover overlap between
independently maintained biology knowledge graphs, request comparisons, approve or reject them
manually, and receive policy-limited similarity results. The registry never has access to private
graph stores, and private entity lists are never exchanged in plaintext to compute similarity.

| Area | v1 decision |
|---|---|
| Participants | 4 simulated verified researchers (Persona A–D) + 1 unverified account (Persona E) |
| Discovery | One-to-many open channels and one-to-one targeted requests |
| Open channels | 24-hour lifetime, wall-clock enforced |
| Approval | Manual, per comparison |
| Public matching | Topic profiles (Jaccard on published topic IDs) |
| Private matching | PSI-CA for entity overlap (OpenMined PSI, ECDH, cardinality-only) |
| Default disclosure | Coarse similarity band |
| Evidence sharing | Deny-by-default endpoint, disabled in v1 |
| Testing | Docker Compose + pytest + Playwright + GitHub Actions |

## 1. Personas (pseudonymous)

Real scientists are cited as *public scientific inspiration* only. Their names never appear as
account owners, approval actors, or participants in fabricated experiments.

| Account | Theme | Inspiration | Verified citation (Crossref, 2026-10-19) |
|---|---|---|---|
| Persona A | Mass spectrometry and proteomics | Matthias Mann | Aebersold & Mann, *Nature* 2003, doi:10.1038/nature01511 |
| Persona B | Protein identification and analytical proteomics | John R. Yates III | Washburn, Wolters & Yates, *Nat Biotechnol* 2001, doi:10.1038/85686 |
| Persona C | Protein interaction networks and AP-MS | Anne-Claude Gingras | Choi et al., *Nat Methods* 2011 (SAINT), doi:10.1038/nmeth.1541 |
| Persona D | Host–pathogen interactions and systems biology | Nevan Krogan | Gordon et al., *Nature* 2020, doi:10.1038/s41586-020-2286-9 |
| Persona E | Unverified visitor (authorization tests only) | none | none |

Persistent UI banner: `Simulated researchers and synthetic knowledge graphs. No real researcher participation.`

## 2. Data

- `data/synthetic/public/`: public discovery profiles and source records. These are the only fixture files the registry image may contain.
- `data/synthetic/private/`: one RDF graph and one label→ID mapping per persona. Each file is mounted only into its own agent.
- `data/synthetic/ground_truth.json`: test-only. Never mounted into any service.
- Each graph has 20–30 entities, 30–50 relationships, 3–5 hypotheses and 5–10 observations, all `is_synthetic=true`.
- Proteins use UniProt accessions (all verified as reviewed entries). Methods use PSI-MI terms (verified via OLS). Topics use the local controlled vocabulary `urn:fkg:topic:*`.
- Normalization scheme `fkg-norm/1.0` is recorded in every graph and in every comparison scope.
- Each graph contains a unique synthetic *canary* entity, used by leak tests.
- Each graph contains a private topic that does not appear in the public profile, also used by leak tests.
- Fixtures are generated deterministically by `scripts/build_fixtures.py`. A test checks that regeneration is byte-identical.

## 3. Comparison contract (`requested_scope`)

```json
{"topics": ["interactomics"], "entity_classes": ["Protein"], "metric": "jaccard",
 "protocol": "psi_ca", "disclosure": "score_only", "normalization": "fkg-norm/1.0"}
```

Both agents must independently authorize the exact scope. The scope cannot be expanded after approval.

Disclosure levels:

| Level | Output | v1 |
|---|---|---|
| `score_only` | Coarse band: low / medium / high, or `insufficient_disclosure` | yes |
| `summary` | Band, set sizes rounded to buckets, and matched *public* topics; no entity IDs | limited |
| `evidence` | Entities, relations, observations, provenance; needs a separate agreement | disabled (HTTP 403) |

## 4. Stage 2: policy-controlled private similarity

1. The requester submits a scope.
2. The owner approves it manually.
3. The registry issues an Ed25519-signed, short-lived, single-use ticket. The ticket is bound to the participants, protocol, scope, both policy versions, result recipients and expiry.
4. Each agent verifies the ticket and re-checks its own current local policy.
5. Each agent extracts its eligible normalized IDs locally.
6. The agents run OpenMined PSI-CA directly over the `peer` network. The registry is not on this network.
7. Only the designated recipient learns the result. If both parties are entitled to it, the protocol runs once in each direction.
8. Before release, each agent re-validates the ticket and policy. A revoked or stale ticket means no release.

Limitations, to be documented in the README and threat model:
- PSI-CA reveals the exact cardinality to the output party, and it reveals set sizes.
- Banding is a display policy, not a cryptographic guarantee.
- The model is semi-honest.
- PSI-CA is an unreviewed integration until an external review is done.

`plaintext-dev` matcher: it is used only when `DEV_PLAINTEXT_MATCHER=1`, which is off in the demo profile. It serves as the correctness oracle in tests and is labeled in the UI.

Anti-probing measures:
- Below 3 matches, the result is `insufficient_disclosure`.
- Minimum eligible set size.
- Per-pair rate limit enforced by the peer agent.
- Scope fingerprints to catch near-duplicate scopes.
- Repeated attempts are audited.
- Outstanding tickets are revoked when a relevant policy changes.

## 5. Contradictions (local only in v1)

Two observations with the same normalized (subject, predicate, object) are classified as one of:
- `supporting`
- `contradictory_candidate`: opposite polarity under a compatible context (cell type, treatment, time point)
- `context_mismatch`
- `insufficient_information`

A contradiction is not proof that either researcher is wrong. Cross-researcher contradiction details require the evidence agreement, so they are not part of v1.

## 6. Architecture

```text
frontend (nginx + React) --edge--> registry (FastAPI) --data--> postgres
                                      |
                                    agents (internal network, no host ports)
                                      |
          agent_a  agent_b  agent_c  agent_d   <--peer (internal; registry excluded)-->
            |        |        |        |
          kg_a     kg_b     kg_c     kg_d      (private named volumes, one per agent)
```

- **Locally:** separate containers and volumes; short-lived signed service tokens with audience, issuer, expiry and replay checks; no private IDs in logs.
- **In deployment:** HTTPS plus mTLS or an equivalent service identity. A Docker network is not a production security boundary.

## 7. Repository layout

```text
plan.md  README.md  docker-compose.yml  .github/workflows/ci.yml
frontend/  registry/  agents/{common,persona_a..d}/
similarity/{public_topics,scoped_baseline,psi_ca}/
data/synthetic/{public,private}/  scripts/  tests/{unit,integration,security,e2e}/  docs/
```

`agents/common` is the single agent image. `agents/persona_*` contain only that persona's configuration.

## 8. State machines, API, screens, permissions

Unchanged from `plan (1).md` sections 5–7, 9 and 10, with these changes:
- `POST /internal/evidence/export` always returns 403 in v1.
- The Matches screen shows a protocol badge and a "what the other party learned" panel.
- Persona E is used for every denial test.

## 9. Phases and gates

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | Repo, compose, fixtures, health page, PSI library smoke test | All services healthy; registry cannot read any private graph; fixture and determinism tests pass |
| 2 | Demo identities (A–E), verified membership, channels, Clock, topic discovery | Visibility matrix for 5 accounts; expiry tested with a controllable clock |
| 3 | Requests, inbox, approvals, versioned policy, idempotency, audit | Non-owner cannot approve; policy tightening invalidates stale approvals |
| 4a | Signed tickets, service tokens, plaintext-dev matcher, ground-truth scores | Exact scores; rejected or pending requests return nothing |
| 4b | PSI-CA between agents, banding, run-in-both-directions results | PSI-CA count equals the plaintext oracle for every fixture pair |
| 4c | Canary leak scan, peer rate limits, scope fingerprints, revoke-during-compute | No canary, or hash of a canary, in registry DB, logs or captured payloads |
| 5 | Eight UI screens | Full journeys A and B work through the UI only |
| 6 | Playwright with 4 + 1 isolated sessions | Repeatable green run, no cross-account leakage |
| 7 | README, threat model, limitations, demo script | Fresh clone → `docker compose up --build` → tests pass |

Work stops at each gate to report test results.

**Ordering:** the web workflows (Phases 2, 3 and 5) may be built before 4b, but the MVP is not called privacy-preserving until 4b and 4c pass.

## 10. Out of scope for v1

Real onboarding of named scientists, scraping, automated messaging, LLMs, federated learning, malicious-secure or threshold PSI, private embeddings, blockchain, Bluetooth or Wi-Fi Direct, evidence export, production SSO.
