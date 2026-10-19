// Captures UI screenshots for review and docs: FKG_SCREENSHOTS=1 npx playwright test
import { expect, test } from "@playwright/test";

const OUT = process.env.FKG_SCREENSHOT_DIR ?? "screenshots";

test("capture screens", async ({ browser }) => {
  const reset = await (await browser.newContext()).newPage();
  await reset.goto("/");
  await reset.getByTestId("reset-demo").click();
  await reset.screenshot({ path: `${OUT}/01-login.png`, fullPage: true });

  const sign = async (persona: string, width = 1280) => {
    const page = await (await browser.newContext({ viewport: { width, height: 900 } })).newPage();
    await page.goto("/");
    await page.getByTestId(`login-${persona}`).click();
    await expect(page.getByTestId("signed-in-as")).toBeVisible();
    return page;
  };

  const a = await sign("persona_a");
  await a.getByTestId("nav-channels").click();
  await a.getByTestId("create-channel").click();
  await a.getByTestId("activate").click();
  await expect(a.getByTestId("channel-status")).toHaveText("ACTIVE");
  await a.screenshot({ path: `${OUT}/02-channels.png`, fullPage: true });

  const b = await sign("persona_b");
  await b.getByTestId("nav-discover").click();
  await b.getByTestId("channel-request-persona_a").click();
  await b.screenshot({ path: `${OUT}/03-discover.png`, fullPage: true });
  await b.getByTestId("channel-form-persona_a-submit").click();

  await a.getByTestId("nav-requests").click();
  await expect(a.getByTestId("inbox-persona_b")).toBeVisible();
  await a.screenshot({ path: `${OUT}/04-inbox.png`, fullPage: true });
  await a.getByTestId("inbox-persona_b").getByTestId("approve").click();

  await b.getByTestId("nav-requests").click();
  await b.getByTestId("tab-outbox").click();
  await b.getByTestId("run").click();
  await expect(b.getByTestId("request-status")).toHaveText("COMPLETED");
  await b.getByTestId("nav-matches").click();
  await expect(b.getByTestId("protocol-badge")).toBeVisible();
  await b.locator("summary").click();
  await b.screenshot({ path: `${OUT}/05-matches.png`, fullPage: true });

  await a.getByTestId("nav-kg").click();
  await expect(a.getByTestId("kg-graph").locator("canvas").first()).toBeVisible();
  await a.waitForTimeout(800);
  await a.screenshot({ path: `${OUT}/06-my-kg.png`, fullPage: true });

  await a.getByTestId("nav-audit").click();
  await a.screenshot({ path: `${OUT}/07-audit.png`, fullPage: true });

  const c = await sign("persona_c", 390);
  await c.getByTestId("nav-directory").click();
  await c.screenshot({ path: `${OUT}/08-directory-phone.png`, fullPage: true });
});
