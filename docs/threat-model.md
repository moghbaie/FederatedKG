# Threat model

This document describes what the FederatedKG MVP protects, against whom, how each protection is enforced and
tested, and what remains open. It covers the **local Docker demonstration**. Where deployment would need more,
it says so.

## Assets

| Asset | Why it matters |
|---|---|
| Private graph contents (entities, relationships, observations, hypotheses) | Unpublished research. The core secret. |
| Which identifiers a researcher holds | Membership in a private set is itself sensitive, even when no other content leaks. |
| Exact overlap counts | Can be combined across queries to infer membership. |
| Policy decisions and consent | Researchers must stay in control of every disclosure. |
| Service and ticket signing keys | They authorize comparisons and authenticate services. |
| Audit integrity | It shows who did what, under which policy version. |

## Actors and trust assumptions

| Actor | Assumed behavior |
|---|---|
| Researcher (requester or owner) | **Honest but curious.** Follows the protocol, but may try to learn more from what they legitimately receive. |
| Probing requester | Sends many or carefully chosen comparisons to infer whether the other side holds specific identifiers. |
| Unverified user (Persona E) | Authenticated, but not entitled to research features. |
| Registry operator | Trusted for identity, approvals, ticket issuing and release gating. **Not** trusted with graph data, and given no technical means to read it. |
| Network attacker (inside the Docker network) | Can observe or replay internal HTTP traffic. |
| Compromised agent | Out of scope for the guarantees below. It holds its own graph and key by design. |

## Trust boundaries

1. Browser ↔ registry, at nginx `/api`.
2. Browser ↔ the owner's own agent, at nginx `/agent/<persona>/owner/graph` only.
3. Registry ↔ agents, on the `agents` network.
4. Agent ↔ agent, on the `peer` network. The registry isn't attached.
5. Each agent ↔ its own volume, holding the private graph and its key.

## Threats, mitigations and evidence

| # | Threat | Mitigation | Verified by |
|---|---|---|---|
| T1 | Registry reads a private graph | No graph mount, no agent key, not on `peer`. Private fixtures excluded from every build context. Agents expose no graph-reading internal endpoint. | `test_isolation.py`, static and live canary scans |
| T2 | One researcher's agent reads another's graph | Each agent mounts only its own graph and key, and refuses a graph owned by another persona | `test_each_agent_holds_only_its_own_graph`, `test_agent_refuses_foreign_graph` |
| T3 | Private identifiers leak during a comparison | PSI-CA exchanges blinded messages only. Result packages carry bands and buckets, and the registry rejects any package with numbers or extra fields. | **Leak scan:** every identifier, SHA-256 and base64 form, across all captured payloads, the database dump and logs. The negative control (plaintext matcher) flags 21 identifiers. |
| T4 | Comparison without consent | Manual approval only. Tickets are issued only for APPROVED requests that pass `execution_check`. Agents re-check their own local policy. | `test_requests.py`, `test_execution.py`, Playwright scenario |
| T5 | Approval used after the owner restricts policy | Policy edits re-check open requests in the same transaction. Tickets are revoked on cancel, expiry or failure. Agents re-check ticket status before compute and before release. The registry re-checks under row locks before storing. | Revoke-during-compute tests (in-process and live), race tests on Postgres |
| T6 | Ticket or token replay or forgery | Service tokens are EdDSA, bound to caller, audience, method, path and body hash, last 60 s, and carry a jti replay cache. Tickets are single use per role, last 5 minutes and are registry-signed. User tokens are EdDSA, and HS256 is refused once keys exist. | `test_protocol.py`, live probes for tampering, replay and impersonation |
| T7 | Unverified or non-party access | Verified-only dependencies. Non-parties get 404 for requests. Result visibility is enforced per consumer. My KG requires the token subject to equal the agent's persona. | Visibility matrix, Persona E tests, owner-view tests |
| T8 | Probing through repeated or near-identical scopes | Per-pair limits on requests (5 / 24 h) and distinct scopes (3 / 24 h) at the registry, plus per-counterpart limits at each agent (10 / 24 h). Duplicate open requests refused. Minimum eligible set size. Below 3 shared items: `insufficient_disclosure`. All refusals audited. | Quota and rate-limit tests, `local_pair_limit_reached` observed live |
| T9 | Double submission and races | Idempotency keys, per-requester row lock, fixed lock order (channel, then request) | Barrier-synchronized race tests, shown to fail without the lock |
| T10 | Expired channel still used | Expiry derived from the clock on every operation, never from a stored flag. Unfinished work expires. | Expiry tests at the API, live and browser levels |
| T11 | Secrets or payloads in logs or audit | The audit stores metadata only. Tokens never appear in logs. Exact counts never leave the agent. | `test_audit_never_stores_tokens`, log scans |
| T12 | Evidence exfiltration | Evidence disclosure is refused at request time. The agent export endpoint always returns 403 in v1. | Scope rejection tests, live probe |

## Residual risks and explicit limitations

- **PSI-CA leakage is inherent.**
  - The output party learns the exact intersection size, and each side learns the other's set size.
  - Bands are a **display policy**, not a cryptographic guarantee.
  - A requester who chooses its input set adversarially (for example, a single identifier) can test membership.
    Minimum set sizes and rate limits slow this down; they don't prevent it.
- **Semi-honest model only.** Malicious-secure PSI, threshold or banded PSI and input certification are out of
  scope.
- **Unreviewed integration.** OpenMined PSI is an established library, but its integration here hasn't had an
  external cryptographic review.
- **The registry is trusted for authorization.** A compromised registry can't read graphs, but it could issue
  tickets for unapproved comparisons. Each agent's local policy still bounds what such a ticket could do.
- **Transport.** Internal traffic is plain HTTP authenticated by signed tokens. A Docker network isn't a security
  boundary in deployment.
- **Identity.** The demo login has no real authentication. OIDC or institutional SSO is required before any real use.
- **Key management.** Keys are generated locally and kept in volumes, with no rotation, revocation list or hardware
  protection.
- **Test-mode features** (adjustable clock, reset, payload capture, injected delay) are on by default **for the
  local demo only**.
- **Availability.** There's no protection against denial of service. A registry crash during a run leaves the
  request RUNNING until it expires.

## Required before any non-demo deployment

1. Set `FKG_TEST_MODE=0`, `FKG_CAPTURE_PAYLOADS=0` and `DEV_PLAINTEXT_MATCHER=0`, and set a strong `POSTGRES_PASSWORD`.
2. Replace demo login with OIDC or institutional SSO, and verify research membership through a trusted source.
3. Use mTLS between all services, with each agent operated inside its own institution's boundary.
4. Manage keys properly: a KMS or HSM, rotation, a published keyring and revocation.
5. Get an external review of the PSI-CA integration and threat model, and consider malicious-secure or threshold
   variants.
6. Run the registry with more than one worker only after moving the test clock out of process memory, or keep test
   mode off.
