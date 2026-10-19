import { expect, test, type Browser, type Page } from "@playwright/test";

// Phase 5 gate: the whole workflow is doable in the browser alone (no curl, no database tools).
// Each researcher uses an isolated browser context (separate storage and session).

async function signIn(browser: Browser, persona: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/");
  await page.getByTestId(`login-${persona}`).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
  await expect(page.getByTestId("banner")).toContainText("No real researcher participation");
  return page;
}

async function resetDemo(browser: Browser) {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/");
  await page.getByTestId("reset-demo").click();
  await expect(page.getByTestId("toast").first()).toContainText("Demo reset");
  await page.context().close();
}

test.beforeEach(async ({ browser }) => resetDemo(browser));

test("journey A: open channel, three requests, three different outcomes, private match", async ({ browser }) => {
  const a = await signIn(browser, "persona_a");
  await a.getByTestId("nav-channels").click();
  await a.getByTestId("create-channel").click();
  const card = a.locator("[data-testid^='my-channel-']").first();
  await expect(card.getByTestId("channel-status")).toHaveText("DRAFT");
  await card.getByTestId("activate").click();
  await expect(card.getByTestId("channel-status")).toHaveText("ACTIVE");
  await expect(card.getByTestId("countdown")).toContainText("23h");

  const requesters = ["persona_b", "persona_c", "persona_d"] as const;
  const pages: Record<string, Page> = {};
  for (const p of requesters) {
    const page = await signIn(browser, p);
    pages[p] = page;
    await page.getByTestId("nav-discover").click();
    const channel = page.getByTestId("channel-persona_a");
    await expect(channel).toBeVisible();
    await expect(channel.getByTestId("topic-match-persona_a")).toBeVisible();
    await channel.getByTestId("channel-request-persona_a").click();
    await channel.getByTestId("channel-form-persona_a-submit").click();
    await expect(page.getByTestId("toast").first()).toContainText("Request sent");
  }

  await a.getByTestId("nav-requests").click();
  await a.getByTestId("inbox-persona_b").getByTestId("approve").click();
  await a.getByTestId("inbox-persona_c").getByTestId("reject").click();
  await expect(a.getByTestId("inbox-persona_b").getByTestId("request-status")).toHaveText("APPROVED");
  await expect(a.getByTestId("inbox-persona_c").getByTestId("request-status")).toHaveText("REJECTED");
  await expect(a.getByTestId("inbox-persona_d").getByTestId("request-status")).toHaveText("PENDING");

  const b = pages.persona_b;
  await b.getByTestId("nav-requests").click();
  await b.getByTestId("tab-outbox").click();
  await b.getByTestId("outbox-persona_a").getByTestId("run").click();
  await expect(b.getByTestId("outbox-persona_a").getByTestId("request-status")).toHaveText("COMPLETED");
  await b.getByTestId("nav-matches").click();
  const match = b.getByTestId("match-persona_a");
  await expect(match.getByTestId("protocol-badge")).toHaveText("PSI-CA private matching");
  await expect(match.getByTestId("band-Protein")).toHaveText(/high|medium|low|insufficient disclosure/);

  for (const [p, status] of [["persona_c", "REJECTED"], ["persona_d", "PENDING"]] as const) {
    const page = pages[p];
    await page.getByTestId("nav-requests").click();
    await page.getByTestId("tab-outbox").click();
    await expect(page.getByTestId("outbox-persona_a").getByTestId("request-status")).toHaveText(status);
    await page.getByTestId("nav-matches").click();
    await expect(page.getByText("No completed comparisons yet.")).toBeVisible();
  }

  await a.getByTestId("nav-audit").click();
  await expect(a.getByTestId("audit-timeline")).toContainText("request.approve");
  await expect(a.getByTestId("audit-timeline")).toContainText("result.release");
});

test("journey B: targeted one-to-one request with manual approval", async ({ browser }) => {
  const c = await signIn(browser, "persona_c");
  await c.getByTestId("nav-directory").click();
  const d = c.getByTestId("directory-persona_d");
  await d.getByTestId("request-persona_d").click();
  await d.getByTestId("scope-topic-interactomics").check();
  await d.getByTestId("scope-class-Interaction").check();
  await d.getByTestId("scope-summary").check();
  await d.getByTestId("scope-visibility-both").check();
  await d.getByTestId("request-form-persona_d-submit").click();
  await expect(c.getByTestId("toast").first()).toContainText("Request sent");

  const dPage = await signIn(browser, "persona_d");
  await expect(dPage.getByTestId("notifications-unread")).toHaveText("1");
  await dPage.getByTestId("nav-requests").click();
  await dPage.getByTestId("inbox-persona_c").getByTestId("approve").click();

  await c.getByTestId("nav-requests").click();
  await c.getByTestId("tab-outbox").click();
  await c.getByTestId("outbox-persona_d").getByTestId("run").click();
  await expect(c.getByTestId("outbox-persona_d").getByTestId("request-status")).toHaveText("COMPLETED");

  for (const [page, other] of [[c, "persona_d"], [dPage, "persona_c"]] as const) {
    await page.getByTestId("nav-matches").click();
    const m = page.getByTestId(`match-${other}`);
    await expect(m.getByTestId("band-Protein")).toHaveText("medium");      // 8 / 32 shared proteins
    await expect(m.getByTestId("band-Interaction")).toHaveText("low");     // 4 / 30 shared interactions
  }
  await c.getByTestId("match-persona_d").getByTestId("contact").click();
  await expect(c.getByTestId("toast").first()).toContainText("notified in the app");
});

test("My KG is local-only and shows public/private nodes and contradiction labels", async ({ browser }) => {
  const a = await signIn(browser, "persona_a");
  await a.getByTestId("nav-kg").click();
  await expect(a.getByTestId("kg-graph").locator("canvas").first()).toBeVisible();
  await expect(a.getByText("public (published topic, 4)")).toBeVisible();
  await expect(a.getByTestId("contradiction-o1-o2")).toContainText("contradictory candidate");
  await expect(a.getByTestId("contradiction-o5-o6")).toContainText("context mismatch");
});

test("unverified Persona E sees only its audit trail", async ({ browser }) => {
  const e = await signIn(browser, "persona_e");
  await expect(e.getByTestId("unverified-notice")).toBeVisible();
  await expect(e.getByTestId("nav-discover")).toHaveCount(0);
  await e.goto("/discover");
  await expect(e).toHaveURL(/\/audit$/);
});
