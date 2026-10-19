import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

// Phase 6 gate: the full four-researcher scenario (+ unverified Persona E), each in an isolated
// browser context with its own session. Run with --repeat-each to check repeatability.

type Persona = "persona_a" | "persona_b" | "persona_c" | "persona_d" | "persona_e";

async function signIn(browser: Browser, persona: Persona): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/");
  await page.getByTestId(`login-${persona}`).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
  return page;
}

/** After the demo clock jumps 24 h, other tabs' 30-minute sessions have expired: sign in again. */
async function resume(page: Page, persona: Persona) {
  await page.goto("/");
  const login = page.getByTestId(`login-${persona}`);
  // Wait until the app settles on either the sign-in page or a still-valid session.
  await expect(login.or(page.getByTestId("signed-in-as"))).toBeVisible();
  if (await login.isVisible()) await login.click();
  await expect(page.getByTestId("signed-in-as")).toHaveText(name(persona));
}

const name = (p: Persona) => `Persona ${p.slice(-1).toUpperCase()}`;

async function sent(page: Page): Promise<void> {
  await page.getByTestId("nav-requests").click();
  await page.getByTestId("tab-outbox").click();
}

async function inbox(page: Page): Promise<void> {
  await page.getByTestId("nav-requests").click();
  await page.getByTestId("tab-inbox").click();
}

function card(page: Page, kind: "inbox" | "outbox", who: Persona, attrs: Record<string, string> = {}): Locator {
  const sel = Object.entries(attrs).map(([k, v]) => `[data-${k}="${v}"]`).join("");
  return page.locator(`[data-testid="${kind}-${who}"]${sel}`);
}

async function requestFromChannel(page: Page, topics: string[], classes: ("Protein" | "Interaction")[]) {
  await page.getByTestId("nav-discover").click();
  const ch = page.getByTestId("channel-persona_a");
  await ch.getByTestId("channel-request-persona_a").click();
  const form = ch.getByTestId("channel-form-persona_a");
  for (const box of await form.locator("[data-testid^='scope-topic-']").all()) {
    const topic = (await box.getAttribute("data-testid"))!.replace("scope-topic-", "");
    await box.setChecked(topics.includes(topic));
  }
  for (const cls of ["Protein", "Interaction"] as const) await form.getByTestId(`scope-class-${cls}`).setChecked(classes.includes(cls));
  await ch.getByTestId("channel-form-persona_a-submit").click();
  await expect(ch.getByTestId("channel-form-persona_a")).toHaveCount(0);
}

async function apiStatus(page: Page, path: string): Promise<number> {
  return page.evaluate(async (p) => {
    const token = sessionStorage.getItem("fkg.token");
    const r = await fetch(p, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    return r.status;
  }, path);
}

test.beforeEach(async ({ browser }) => {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/");
  await page.getByTestId("reset-demo").click();
  await expect(page.getByTestId("toast").first()).toContainText("Demo reset");
  await page.context().close();
});

test("four researchers: approvals, pause, tightening, 24 h expiry, targeted flow, no leakage", async ({ browser }) => {
  test.setTimeout(300_000); // one long scenario across five browser contexts
  const [a, b, c, d, e] = await Promise.all(
    (["persona_a", "persona_b", "persona_c", "persona_d", "persona_e"] as const).map((p) => signIn(browser, p)));

  // Each isolated context holds only its own session.
  for (const [page, p] of [[a, "persona_a"], [b, "persona_b"], [c, "persona_c"], [d, "persona_d"], [e, "persona_e"]] as const) {
    await expect(page.getByTestId("signed-in-as")).toHaveText(name(p));
  }

  // ---- 1. A opens a 24-hour, topics-only, research-audience channel ---------------------------------
  await test.step("A opens a channel", async () => {
    await a.getByTestId("nav-channels").click();
    await a.getByTestId("create-channel").click();
    const ch = a.locator("[data-testid^='my-channel-']").first();
    await ch.getByTestId("activate").click();
    await expect(ch.getByTestId("channel-status")).toHaveText("ACTIVE");
    await expect(ch.getByTestId("countdown")).toContainText("23h");
  });
  const channel = a.locator("[data-testid^='my-channel-']").first();

  // ---- 2. B, C, D discover it and request; E cannot -----------------------------------------------------
  await test.step("B, C and D request; E cannot discover", async () => {
    await requestFromChannel(b, ["mass_spectrometry"], ["Protein"]);
    await requestFromChannel(c, ["mass_spectrometry"], ["Protein"]);
    await requestFromChannel(d, ["proteomics"], ["Protein"]);
    await expect(e.getByTestId("nav-discover")).toHaveCount(0);
    await e.goto("/discover");
    await expect(e).toHaveURL(/\/audit$/);
    expect(await apiStatus(e, "/api/v1/channels")).toBe(403);
  });

  // ---- 3. A approves B, rejects C, leaves D pending; only B gets a result ---------------------------------
  await test.step("three requesters, three outcomes", async () => {
    await inbox(a);
    await card(a, "inbox", "persona_b").getByTestId("approve").click();
    await card(a, "inbox", "persona_c").getByTestId("reject").click();
    await expect(card(a, "inbox", "persona_d").getByTestId("request-status")).toHaveText("PENDING");

    await sent(b);
    await card(b, "outbox", "persona_a").getByTestId("run").click();
    await expect(card(b, "outbox", "persona_a").getByTestId("request-status")).toHaveText("COMPLETED");
    await b.getByTestId("nav-matches").click();
    await expect(b.getByTestId("match-persona_a").getByTestId("protocol-badge")).toHaveText("PSI-CA private matching");
    await expect(b.getByTestId("match-persona_a").getByTestId("band-Protein")).toHaveText("high"); // 12 / 26 shared

    for (const [page, status] of [[c, "REJECTED"], [d, "PENDING"]] as const) {
      await sent(page);
      await expect(card(page, "outbox", "persona_a").getByTestId("request-status")).toHaveText(status);
      await page.getByTestId("nav-matches").click();
      await expect(page.getByText("No completed comparisons yet.")).toBeVisible();
    }
    // A approved a requester-only comparison: A sees that a match exists but not its result.
    await a.getByTestId("nav-matches").click();
    await expect(a.getByTestId("match-persona_b")).toContainText("keep this result to themselves");
    await expect(a.getByTestId("match-persona_b").getByTestId("band-Protein")).toHaveCount(0);
  });

  // ---- 4. A second, approved-but-not-run request from B ---------------------------------------------------
  const staleAttrs = { classes: "Interaction", topics: "mass_spectrometry" };
  await test.step("B's second request is approved but not yet run", async () => {
    await requestFromChannel(b, ["mass_spectrometry"], ["Interaction"]);
    await inbox(a);
    await card(a, "inbox", "persona_b", staleAttrs).getByTestId("approve").click();
    await sent(b);
    await expect(card(b, "outbox", "persona_a", staleAttrs).getByTestId("request-status")).toHaveText("APPROVED");
    await expect(card(b, "outbox", "persona_a", staleAttrs).getByTestId("run")).toBeEnabled();
  });

  // ---- 5. A pauses: new requests blocked, approved work cannot run ----------------------------------------
  await test.step("pause blocks new requests and execution", async () => {
    await a.getByTestId("nav-channels").click();
    await channel.getByTestId("pause").click();
    await expect(channel.getByTestId("channel-status")).toHaveText("PAUSED");
    await expect(card(b, "outbox", "persona_a", staleAttrs).getByTestId("blocked-reason")).toContainText("channel paused");
    await expect(card(b, "outbox", "persona_a", staleAttrs).getByTestId("run")).toBeDisabled();
    await c.getByTestId("nav-discover").click();
    await expect(c.getByText("No open channels right now.")).toBeVisible();
  });

  // ---- 6. A tightens the policy while paused: stale approval invalidated -------------------------------------
  await test.step("tightening invalidates the stale approval only", async () => {
    await channel.getByTestId("edit-policy").click();
    await channel.locator("[data-testid$='-topic-mass_spectrometry']").uncheck();
    await channel.getByTestId("save-policy").click();
    await expect(channel).toContainText("policy v2");
    await channel.getByRole("button", { name: "History" }).click();
    await expect(channel.locator("table")).toContainText("v2");

    const stale = card(b, "outbox", "persona_a", staleAttrs);
    await expect(stale.getByTestId("request-status")).toHaveText("CANCELLED");
    await expect(stale).toContainText("policy incompatible");
    // The earlier, completed disclosure is not erased retroactively.
    await expect(card(b, "outbox", "persona_a", { classes: "Protein" }).getByTestId("request-status")).toHaveText("COMPLETED");
    // D's pending proteomics request still fits version 2.
    await sent(d);
    await expect(card(d, "outbox", "persona_a").getByTestId("request-status")).toHaveText("PENDING");
  });

  // ---- 7. Resume: only the narrower topics are offered; A approves D (not run) ---------------------------------
  await test.step("resume with the tightened policy", async () => {
    await channel.getByTestId("resume").click();
    await expect(channel.getByTestId("channel-status")).toHaveText("ACTIVE");
    await c.getByTestId("nav-discover").click();
    const ch = c.getByTestId("channel-persona_a");
    await ch.getByTestId("channel-request-persona_a").click();
    await expect(ch.getByTestId("scope-topic-proteomics")).toBeVisible();
    await expect(ch.getByTestId("scope-topic-mass_spectrometry")).toHaveCount(0);

    await inbox(a);
    await card(a, "inbox", "persona_d").getByTestId("approve").click();
    await sent(d);
    await expect(card(d, "outbox", "persona_a").getByTestId("request-status")).toHaveText("APPROVED");
  });

  // ---- 8. 24 hours pass: channel expires, unfinished work is cancelled, prior results remain ------------------
  await test.step("24-hour expiry", async () => {
    await a.getByTestId("clock-24h").click();
    await a.getByTestId("nav-channels").click();
    await expect(channel.getByTestId("channel-status")).toHaveText("EXPIRED");
    await expect(channel.getByTestId("pause")).toHaveCount(0);

    await resume(d, "persona_d");
    await sent(d);
    await expect(card(d, "outbox", "persona_a").getByTestId("request-status")).toHaveText("EXPIRED");
    await expect(card(d, "outbox", "persona_a").getByTestId("run")).toHaveCount(0);

    await resume(b, "persona_b");
    await b.getByTestId("nav-discover").click();
    await expect(b.getByText("No open channels right now.")).toBeVisible();
    await b.getByTestId("nav-matches").click();
    await expect(b.getByTestId("match-persona_a").getByTestId("band-Protein")).toHaveText("high");
  });

  // ---- 9. Targeted one-to-one: C -> D with manual approval ---------------------------------------------------
  await test.step("targeted C to D", async () => {
    await resume(c, "persona_c");
    await c.getByTestId("nav-directory").click();
    const target = c.getByTestId("directory-persona_d");
    await target.getByTestId("request-persona_d").click();
    await target.getByTestId("scope-class-Interaction").check();
    await target.getByTestId("scope-summary").check();
    await target.getByTestId("scope-visibility-both").check();
    await target.getByTestId("request-form-persona_d-submit").click();

    await inbox(d);
    await card(d, "inbox", "persona_c").getByTestId("approve").click();
    await sent(c);
    await card(c, "outbox", "persona_d").getByTestId("run").click();
    await expect(card(c, "outbox", "persona_d").getByTestId("request-status")).toHaveText("COMPLETED");
    for (const [page, other] of [[c, "persona_d"], [d, "persona_c"]] as const) {
      await page.getByTestId("nav-matches").click();
      await expect(page.getByTestId(`match-${other}`).getByTestId("band-Protein")).toHaveText("medium");
      await expect(page.getByTestId(`match-${other}`).getByTestId("band-Interaction")).toHaveText("low");
    }
  });

  // ---- 10. No cross-account leakage -----------------------------------------------------------------------
  await test.step("no cross-account leakage", async () => {
    await sent(c);
    const cRequestId = await card(c, "outbox", "persona_d").getAttribute("data-request-id");
    expect(cRequestId).toBeTruthy();
    await resume(a, "persona_a");
    expect(await apiStatus(a, `/api/v1/requests/${cRequestId}`)).toBe(404);          // not a party
    expect(await apiStatus(a, `/api/v1/requests/${cRequestId}/result`)).toBe(404);
    expect(await apiStatus(b, "/agent/persona_a/owner/graph")).toBe(403);             // someone else's KG
    expect(await apiStatus(b, "/agent/persona_b/owner/graph")).toBe(200);             // own KG
    expect(await apiStatus(b, "/agent/persona_b/internal/health")).toBe(404);         // nothing else proxied

    await resume(e, "persona_e");
    for (const path of ["/api/v1/channels", "/api/v1/requests/inbox", "/api/v1/researchers", `/api/v1/requests/${cRequestId}`]) {
      expect(await apiStatus(e, path)).toBe(403);
    }
    expect(await apiStatus(e, "/agent/persona_a/owner/graph")).toBe(403);

    // B never sees requests addressed to or sent by others.
    await inbox(b);
    await expect(b.locator("[data-testid^='inbox-']")).toHaveCount(0);
    await sent(b);
    await expect(b.locator("[data-testid^='outbox-']:not([data-testid='outbox-persona_a'])")).toHaveCount(0);
  });

  // ---- 11. The audit trail tells the story ---------------------------------------------------------------
  await test.step("audit trail", async () => {
    await a.getByTestId("nav-audit").click();
    const timeline = a.getByTestId("audit-timeline");
    for (const action of ["channel.pause", "channel.update", "request.invalidate", "request.reject", "result.release", "request.expire"]) {
      await expect(timeline).toContainText(action);
    }
  });
});
