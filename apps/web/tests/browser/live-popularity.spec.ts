import { test, expect, type Page, type Route } from "@playwright/test";

const endpoint = "**/firmware/*/popularity/live";
const metric = (page: Page) => page.locator(".firmware-popularity");
const reply = (route: Route, payload: unknown, status = 200) => route.fulfill({ status, json: payload, headers: { "Access-Control-Allow-Origin": "*" } });
const envelope = (outcome = "fresh", id = "fixture-00") => {
  const index = Number(id.slice(-2));
  const identity = { source_url: `https://github.com/atlas-fixture/project-${index}`, repo_id: 100 + index };
  return { firmware_id: id, outcome, catalog: { ...identity, stars: 24, forks: index, github_as_of: "2026-11-06T17:00:00Z" },
    github: ["unavailable", "ineligible"].includes(outcome) ? null
      : { ...identity, stars: 0, forks: 0, observed_at: "2026-11-07T01:00:00Z" }, retry_after_seconds: 120 };
};
function gate() {
  let release!: () => void;
  const promise = new Promise<void>(resolve => { release = resolve; });
  return { release, promise };
}
const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-11-07T01:00:30Z"));
  errors.set(page, []);
  page.on("pageerror", error => errors.get(page)!.push(error.message));
  await page.route(/google-analytics|googletagmanager|raw\.githubusercontent|\/api\/intent/, route => route.abort());
});
test.afterEach(async ({ page }) => { expect(errors.get(page)).toEqual([]); });

for (const [outcome, label] of [["fresh", "Checked this visit"], ["cached", "Cached check"], ["stale", "Last successful check"]]) {
  test(`${outcome} shows its dated source, preserves zeros and focus, and makes one request`, async ({ page }) => {
    const pending = gate(); let requests = 0;
    await page.route(endpoint, async route => { requests++; await pending.promise; await reply(route, envelope(outcome)); });
    try {
      await page.goto("/firmware/fixture-00");
      await expect.poll(() => requests).toBe(1);
      await expect(metric(page)).toContainText("24 stars · 0 forks");
      const source = page.getByRole("link", { name: "View the repo", exact: true });
      await source.focus();
      pending.release();
      await expect(metric(page)).toContainText("0 stars · 0 forks");
      await expect(metric(page)).toContainText(`GitHub repo · as of 2026-11-07 01:00 UTC · ${label}`);
      await expect(source).toHaveAttribute("href", "https://github.com/atlas-fixture/project-0");
      await expect(source).toBeFocused();
      await expect(metric(page).getByRole("status")).toHaveText("Repository counts updated: 0 stars and 0 forks.");
      await page.evaluate(() => { window.dispatchEvent(new Event("focus")); window.dispatchEvent(new Event("online")); });
      await page.waitForTimeout(250);
      expect(requests).toBe(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await expect(metric(page)).toBeInViewport();
      await page.screenshot({ path: test.info().outputPath(`${outcome}.png`) });
    } finally { pending.release(); }
  });
}

for (const outcome of ["unavailable", "ineligible", "wrong-identity", "http-error", "network-error", "oversize"]) {
  test(`${outcome} retains the catalog and never retries`, async ({ page }) => {
    let requests = 0;
    await page.route(endpoint, route => {
      requests++;
      if (outcome === "network-error") return route.abort();
      if (outcome === "oversize") return route.fulfill({ body: " ".repeat(17000), headers: { "Access-Control-Allow-Origin": "*" } });
      return reply(route, outcome === "wrong-identity" ? envelope("fresh", "fixture-01") : envelope(outcome), outcome === "http-error" ? 503 : 200);
    });
    await page.goto("/firmware/fixture-00");
    await expect.poll(() => requests).toBe(1);
    await page.waitForTimeout(250);
    await expect(metric(page)).toContainText("24 stars · 0 forks");
    await expect(metric(page)).toContainText("GitHub repo · as of 2026-11-06 17:00 UTC");
    await expect(metric(page).getByRole("status")).toBeEmpty();
    await page.clock.install();
    await page.clock.fastForward(130_000);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    expect(requests).toBe(1);
  });
}

async function observeAborts(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch;
    Object.assign(window, { popularityAborts: 0 });
    window.fetch = (input, init) => {
      if (String(input).endsWith("/popularity/live")) init?.signal?.addEventListener("abort", () => {
        const tracked = window as typeof window & { popularityAborts: number };
        tracked.popularityAborts++;
      });
      return original(input, init);
    };
  });
}
test("the ten-second deadline aborts a pending request and retains the catalog", async ({ page }) => {
  const pending = gate(); let requests = 0;
  await observeAborts(page);
  await page.clock.install();
  await page.route(endpoint, async route => { requests++; await pending.promise; await reply(route, envelope()).catch(() => {}); });
  try {
    await page.goto("/firmware/fixture-00");
    await expect.poll(() => requests).toBe(1);
    await page.clock.fastForward(10_100);
    await expect.poll(() => page.evaluate(() => (window as typeof window & { popularityAborts: number }).popularityAborts)).toBe(1);
    pending.release();
    await expect(metric(page)).toContainText("24 stars · 0 forks");
    await page.clock.fastForward(130_000);
    expect(requests).toBe(1);
  } finally { pending.release(); }
});

test("leaving aborts; a late response cannot change the next firmware or a repeat visit", async ({ page }) => {
  const pending = gate(); let firstRequests = 0, secondRequests = 0;
  await observeAborts(page);
  await page.route(endpoint, async route => {
    if (route.request().url().includes("fixture-00")) { firstRequests++; if (firstRequests === 1) await pending.promise; await reply(route, envelope()).catch(() => {}); }
    else { secondRequests++; await reply(route, envelope("unavailable", "fixture-01")); }
  });
  try {
    await page.goto("/firmware/fixture-00");
    await expect.poll(() => firstRequests).toBe(1);
    await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Firmware", exact: true }).click();
    await expect.poll(() => page.evaluate(() => (window as typeof window & { popularityAborts: number }).popularityAborts)).toBe(1);
    await page.locator('a[href="/firmware/fixture-01"]').first().click();
    await expect.poll(() => secondRequests).toBe(1);
    pending.release();
    await expect(metric(page)).toContainText("23 stars · 1 forks");
    await expect(metric(page)).not.toContainText("Checked this visit");
    await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Firmware", exact: true }).click();
    await page.locator('a[href="/firmware/fixture-00"]').first().click();
    await expect.poll(() => firstRequests).toBe(2);
    await expect(metric(page)).toContainText("Checked this visit");
  } finally { pending.release(); }
});

test("uncited firmware makes no request and keeps its historical date", async ({ page }) => {
  let requests = 0;
  await page.route(endpoint, route => { requests++; return route.abort(); });
  await page.goto("/firmware/fixture-02");
  await expect(metric(page)).toContainText("historical snapshot 2026-09-20");
  await page.waitForTimeout(250);
  expect(requests).toBe(0);
});

test("server HTML remains useful with JavaScript disabled", async ({ browser, baseURL }, testInfo) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL, viewport: testInfo.project.use.viewport });
  let requests = 0;
  await context.route(endpoint, route => { requests++; return route.abort(); });
  try {
    const page = await context.newPage();
    await page.goto("/firmware/fixture-00");
    await expect(metric(page)).toContainText("24 stars · 0 forks");
    await expect(metric(page)).toContainText("GitHub repo · as of 2026-11-06 17:00 UTC");
    await expect(page.getByRole("link", { name: "View the repo", exact: true })).toHaveAttribute("href", "https://github.com/atlas-fixture/project-0");
    expect(requests).toBe(0);
  } finally { await context.close(); }
});
