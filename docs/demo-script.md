# Demo script

There are two ways to show FederatedKG, and both start from a known state.

- **Narrated API demo (2 minutes, no clicking).** It resets the demo, runs journeys A and B with the pause,
  tightening and 24-hour expiry, and prints what each researcher can see:

  ```sh
  uv run python scripts/demo.py
  ```

- **Live click-through (10–15 minutes).** Follow the steps below in five browser windows. Use separate private or
  incognito windows, or separate browser profiles, because each tab keeps its own session.

## Before you start

1. Run `docker compose up -d --build --wait` and open http://localhost:8080.
2. Click **Reset demo** on the sign-in page.
3. Open five windows and sign in as Persona A, B, C, D and E.
4. Point out the banner. Every account, graph and observation is synthetic. The cited scientists are research-theme
   inspirations only, not participants.

## Part 1: what each researcher has

- **A → My KG.** A's private graph is served directly by A's agent, never by the registry. Published topics (green)
  are the only public part. The local contradiction check flags a fabricated contradiction (o1 vs o2) and explains
  why that isn't proof of error.
- **B → My KG for A's graph?** Not possible: only A's own session can open A's graph.
- **E** sees only an audit page. Unverified accounts can't discover or request anything.

## Part 2: one-to-many channel (Journey A)

1. **A → My channels.** Keep *proteomics* and *mass spectrometry*, then **Create draft** and **Activate**. Point out
   the 24-hour countdown, the topics-only visibility and manual approval.
2. **B, C, D → Discover.** Each sees A's channel topics and a topic-match score (B 0.50, C 0.17, D 0.00). Nothing
   from A's graph is shown.
3. Each sends a request: B and C on *mass spectrometry*, D on *proteomics*.
4. **A → Requests.** Approve B, reject C, and leave D pending.
5. **B → Requests → Sent → Run comparison.** The two agents run PSI-CA directly and no entity list is exchanged.
6. **B → Matches.** Protein overlap is **high**. Open "What each side learned": A's agent learned B's set size, but not
   the overlap or any identifier.
7. **C → Matches** shows nothing (rejected). **D → Matches** shows nothing (pending). **A → Matches** shows that a
   match exists, but B kept the result.

## Part 3: owner control

1. **B → Discover.** Request again with *Interactions* only, and have **A** approve it. Don't run it yet.
2. **A → My channels → Pause.** In **B → Sent**, the run button is disabled ("channel paused"), and the channel
   disappears from **C → Discover**.
3. **A → Edit policy.** Untick *mass spectrometry*, then **Save as version 2**. B's second request becomes
   **CANCELLED — policy incompatible**. B's earlier result is unchanged, because past disclosures aren't erased.
   D's pending *proteomics* request still fits. Click **History** to show both versions.
4. **A → Resume**, then approve D's request.
5. **A → +24 h** (demo clock). The channel shows **EXPIRED**, and D's approved-but-unrun request expires. Other
   windows must sign in again, because their 30-minute sessions expired on the same clock.

## Part 4: one-to-one (Journey B)

1. **C → Directory → Persona D → Request comparison.** Choose *interactomics*, Proteins + Interactions, **Summary**,
   **Both of us**.
2. **D** receives a notification. Go to **Requests**, then **Approve**.
3. **C → Sent → Run.** Both C and D see Proteins **medium** and Interactions **low**, plus set-size ranges, each
   computed and signed by their own agent.
4. **C → Request contact.** D gets an in-app notice. Nothing is ever sent automatically or outside the app.

## Part 5: accountability

- **A → Audit.** Every policy version, decision, run, release, invalidation and expiry is listed, with the policy
  version each one applied to.
- **E → Audit → Denials.** E's refused attempts are recorded.

## Talking points on privacy

- **The registry never sees a graph.** It has no mount, no agent key and no route to the peer network. Tests scan
  containers, payloads, logs and the database for planted canary identifiers.
- **PSI-CA reveals set sizes and, to the output agent, the exact overlap.** Bands are a display policy, not a
  cryptographic guarantee. See [threat-model.md](threat-model.md).
