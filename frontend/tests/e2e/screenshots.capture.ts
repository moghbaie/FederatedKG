// Captures the docs/screenshots walkthrough: FKG_SCREENSHOTS=1 npx playwright test
import { expect, test, type Browser, type Page } from "@playwright/test";

const OUT = process.env.FKG_SCREENSHOT_DIR ?? "../docs/screenshots";

async function shot(page: Page, name: string) {
  // Full-page captures render sticky elements mid-page; pin the banner to the top for documentation.
  await page.addStyleTag({ content: ".banner{position:static !important} .toasts{display:none !important}" });
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

async function signIn(browser: Browser, persona: string, width = 1280): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width, height: 860 }, colorScheme: "light" })).newPage();
  await page.goto("/");
  await page.getByTestId(`login-${persona}`).click();
  await expect(page.getByTestId("signed-in-as")).toBeVisible();
  return page;
}

test("capture walkthrough screens", async ({ browser }) => {
  test.setTimeout(240_000);
  const start = await (await browser.newContext({ viewport: { width: 1280, height: 860 } })).newPage();
  await start.goto("/");
  await start.getByTestId("reset-demo").click();
  await expect(start.getByTestId("system-status")).toHaveText("all services healthy");
  await shot(start, "01-sign-in");

  const a = await signIn(browser, "persona_a");
  await a.getByTestId("nav-kg").click();
  await expect(a.getByTestId("kg-graph").locator("canvas").first()).toBeVisible();
  await a.waitForTimeout(1000);
  await shot(a, "02-my-kg");

  const c = await signIn(browser, "persona_c");
  await c.getByTestId("nav-directory").click();
  await expect(c.getByTestId("directory-persona_d")).toBeVisible();
  await shot(c, "03-directory");

  await a.getByTestId("nav-channels").click();
  await a.getByTestId("create-channel").click();
  await a.getByTestId("activate").click();
  await expect(a.getByTestId("channel-status")).toHaveText("ACTIVE");
  await shot(a, "04-my-channels");

  const b = await signIn(browser, "persona_b");
  await b.getByTestId("nav-discover").click();
  await b.getByTestId("channel-request-persona_a").click();
  await b.getByTestId("scope-class-Interaction").check();
  await shot(b, "05-discover-request");
  await b.getByTestId("channel-form-persona_a-submit").click();

  await a.getByTestId("nav-requests").click();
  await expect(a.getByTestId("inbox-persona_b")).toBeVisible();
  await shot(a, "06-requests-inbox");
  await a.getByTestId("inbox-persona_b").getByTestId("approve").click();

  await b.getByTestId("nav-requests").click();
  await b.getByTestId("tab-outbox").click();
  await expect(b.getByTestId("run")).toBeEnabled();
  await shot(b, "07-requests-sent");
  await b.getByTestId("run").click();
  await expect(b.getByTestId("request-status")).toHaveText("COMPLETED");
  await b.getByTestId("nav-matches").click();
  await expect(b.getByTestId("protocol-badge")).toBeVisible();
  await b.locator("summary").click();
  await shot(b, "08-matches");

  await a.getByTestId("nav-channels").click();
  await a.getByTestId("pause").click();
  await a.getByTestId("edit-policy").click();
  await a.locator("[data-testid^='my-channel-'] [data-testid$='-topic-mass_spectrometry']").uncheck();
  await a.getByTestId("save-policy").click();
  await expect(a.locator("[data-testid^='my-channel-']")).toContainText("policy v2");
  await a.getByRole("button", { name: "History" }).click();
  await shot(a, "09-paused-and-tightened");

  await a.getByTestId("clock-24h").click();
  await expect(a.getByTestId("channel-status")).toHaveText("EXPIRED");
  await shot(a, "10-expired");
  await a.getByTestId("nav-audit").click();
  await expect(a.getByTestId("audit-timeline")).toContainText("channel.update");
  await shot(a, "11-audit");

  const e = await signIn(browser, "persona_e");
  // E tries research-only endpoints (as a curious client would); each refusal is audited.
  await e.evaluate(async () => {
    const auth = { Authorization: `Bearer ${sessionStorage.getItem("fkg.token")}` };
    for (const p of ["/api/v1/channels", "/api/v1/researchers"]) await fetch(p, { headers: auth });
  });
  await e.reload();
  await e.getByRole("tab", { name: "Denials" }).click();
  await expect(e.getByTestId("audit-timeline")).toContainText("access.verified_only");
  await shot(e, "12-unverified-persona-e");

  const phone = await signIn(browser, "persona_d", 390);
  await phone.getByTestId("nav-directory").click();
  await shot(phone, "13-phone-directory");
});
