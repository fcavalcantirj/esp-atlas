import { test, expect, type Page, type Route } from "@playwright/test";
import { board, build, guide, intent } from "../fixtures/catalog.mjs";
import { SORT_OPTIONS } from "../../lib/firmware-sort";

const errors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  errors.set(page, []);
  page.on("pageerror", error => errors.get(page)!.push(error.message));
  await page.route(/google-analytics|googletagmanager/, route => route.abort());
});
test.afterEach(async ({ page }) => { expect(errors.get(page)).toEqual([]); });
const answer = (page: Page) => page.getByRole("region", { name: "Your atlas answer", exact: true });
const result = (page: Page) => page.getByRole("region", { name: "Results", exact: true });
const tracker = (page: Page) => page.getByRole("heading", { name: "Satellite/ISS Tracker", exact: true });
const json = (route: Route, payload: unknown, status = 200) => route.fulfill({ status, json: payload, headers: { "Access-Control-Allow-Origin": "*" } });
function gate() {
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  return { waiting, release };
}
async function ask(page: Page, text = "a gps tracker") {
  await page.getByLabel("Tell me what you want to build or run…").fill(text);
  await page.getByRole("button", { name: "Go", exact: true }).click();
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

async function oneLoadingMessage(page: Page, text: string) {
  const status = page.getByRole("status");
  await expect(status).toHaveCount(1);
  await expect(status).toHaveText(text);
  await expect(status).toHaveAttribute("aria-atomic", "true");
  expect(await status.evaluate(element => element.closest('[aria-busy="true"]') === null)).toBe(true);
  await expect(answer(page).getByText(text, { exact: true })).toBeInViewport();
  // A visually clipped live region remains accessible, but must not paint a
  // second readable message. Check geometry rather than Playwright :visible,
  // which also matches the clipped one-pixel screen-reader announcement.
  const readableCopies = await page.getByText(text, { exact: true }).evaluateAll(elements => elements.filter(element => {
    const bounds = element.getBoundingClientRect();
    return bounds.width > 1 && bounds.height > 1;
  }).length);
  expect(readableCopies).toBe(1);
  expect((await page.locator("body").ariaSnapshot()).split(text).length - 1).toBe(1);
  await expect(page.getByRole("button", { name: "Searching…", exact: true })).toBeDisabled();
  await noOverflow(page);
}

for (const kind of ["firmware", "unmapped"] as const) {
  test(`${kind} progress appears and is announced once through parsing, failure, retry and repeated submission`, async ({ page }) => {
    const attempts = Array.from({ length: 3 }, () => ({ parsing: gate(), loading: gate() }));
    let intentRequests = 0, guideRequests = 0;
    await page.route("**/intent", async route => {
      const attempt = attempts[intentRequests++];
      await attempt.parsing.waiting;
      await json(route, { ...intent, kind });
    });
    await page.route(kind === "firmware" ? "**/run/*" : "**/build", async route => {
      const index = guideRequests++;
      await attempts[index].loading.waiting;
      await json(route, index === 0 ? { detail: "Fixture unavailable" } : kind === "firmware" ? guide : build, index === 0 ? 503 : 200);
    });
    const text = kind === "firmware" ? "a gps tracker" : "Plant health monitor";
    try {
      await page.goto("/");
      for (let index = 0; index < attempts.length; index++) {
        if (index === 1) await page.getByRole("button", { name: "Try again", exact: true }).click();
        else await ask(page, text);
        await oneLoadingMessage(page, "Reading your request…");
        await expect(answer(page)).toBeFocused();
        attempts[index].parsing.release();
        await oneLoadingMessage(page, kind === "firmware" ? "Finding recorded recipes…" : "Working out what you need…");
        if (index === 0) await page.screenshot({ path: test.info().outputPath("loading.png") });
        const input = page.getByLabel("Tell me what you want to build or run…");
        await input.focus();
        await input.press("Enter");
        expect(intentRequests).toBe(index + 1);
        expect(guideRequests).toBe(index + 1);
        attempts[index].loading.release();
        await expect(page.getByRole("status")).toHaveText(index === 0
          ? "The guide could not be loaded. You can try again." : "Your guide is ready.");
        await expect(input).toBeFocused();
        await expect(page.getByRole("button", { name: "Go", exact: true })).toBeEnabled();
        await expect(answer(page).locator(".results-loading")).toHaveCount(0);
        if (index === 0) await expect(answer(page).getByRole("heading", { name: "We couldn't load this guide" })).toBeVisible();
        else await expect(kind === "firmware" ? tracker(page)
          : page.getByRole("heading", { name: "To build a fixture project, you need" })).toBeVisible();
      }
    } finally {
      attempts.forEach(attempt => { attempt.parsing.release(); attempt.loading.release(); });
    }
  });
}

test("GPS guide is visible and focused; repeated queries and board/guide transitions show only the current answer", async ({ page }) => {
  let requests = 0;
  await page.route("**/intent", route => {
    requests++;
    const query = route.request().postDataJSON().query;
    return json(route, query === "boards" ? { ...intent, kind: "filters", filters: {} } : intent);
  });
  await page.goto("/");
  await ask(page);
  await expect(tracker(page)).toBeInViewport();
  await expect(answer(page)).toBeFocused();
  await expect(page.locator(".examples")).toHaveCount(0);
  await expect(page.getByText("Start with a question", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Unverified", { exact: true })).toBeVisible();
  await expect(page.getByText("Fit unconfirmed", { exact: true })).toBeVisible();
  await ask(page);
  await expect(tracker(page)).toBeInViewport();
  await expect.poll(() => requests).toBe(2);
  await ask(page, "boards");
  await expect(result(page).getByRole("link", { name: "Fixture board" })).toBeVisible();
  await expect(tracker(page)).toHaveCount(0);
  await ask(page);
  await expect(tracker(page)).toBeInViewport();
  await expect(result(page)).toHaveCount(0);
  await noOverflow(page);
});

test("loading is visible and disables submit; completing a guide never steals focus back from the user", async ({ page }) => {
  const intentGate = gate(), guideGate = gate();
  let guideRequests = 0;
  await page.route("**/intent", async route => { await intentGate.waiting; await json(route, intent); });
  await page.route("**/run/*", async route => { guideRequests++; await guideGate.waiting; await json(route, guide); });
  await page.goto("/");
  await ask(page);
  await expect(answer(page)).toContainText("Reading your request");
  await expect(answer(page)).toBeFocused();
  await expect(page.getByRole("button", { name: "Searching…", exact: true })).toBeDisabled();
  intentGate.release();
  await expect.poll(() => guideRequests).toBe(1);
  await expect(answer(page)).toContainText("Finding recorded recipes");
  const input = page.getByLabel("Tell me what you want to build or run…");
  await input.focus();
  await input.press("Enter");
  expect(guideRequests).toBe(1);
  guideGate.release();
  await expect(tracker(page)).toBeVisible();
  await expect(input).toBeFocused();
});

for (const failure of ["http", "network", "malformed"] as const) {
  test(`intent ${failure} failure explains keyword fallback; empty and failed search remain visible and retryable`, async ({ page }) => {
    await page.route("**/intent", route => failure === "network" ? route.abort("failed")
      : json(route, failure === "http" ? { detail: "Unavailable" } : { kind: "filters", filters: null }, failure === "http" ? 503 : 200));
    let searches = 0;
    await page.route("**/search?*", route => json(route, ++searches === 1 ? { detail: "Unavailable" } : { results: [] }, searches === 1 ? 503 : 200));
    await page.goto("/");
    await ask(page);
    await expect(answer(page)).toContainText("keyword matches instead");
    await expect(answer(page).getByRole("heading", { name: "The API did not answer" })).toBeInViewport();
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await expect(answer(page)).toContainText("No parts match");
    await expect(answer(page)).toBeFocused();
  });
  for (const kind of ["firmware", "unmapped"] as const) {
    test(`${kind} guide ${failure} failure provides a working retry`, async ({ page }) => {
      await page.route("**/intent", route => json(route, { ...intent, kind }));
      let attempts = 0;
      await page.route(kind === "firmware" ? "**/run/*" : "**/build", route => {
        if (++attempts > 1) return json(route, kind === "firmware" ? guide : build);
        return failure === "network" ? route.abort("failed") : json(route, { boards: [null] }, failure === "http" ? 503 : 200);
      });
      await page.goto("/");
      await ask(page);
      await expect(page.getByRole("heading", { name: "We couldn't load this guide" })).toBeInViewport();
      await page.getByRole("button", { name: "Try again", exact: true }).click();
      await expect(kind === "firmware" ? tracker(page) : page.getByRole("heading", { name: "To build a fixture project, you need" })).toBeInViewport();
      expect(attempts).toBe(2);
    });
  }
}

test("build guide stays primary; a late guide and secondary search cannot replace a newer spec answer", async ({ page }) => {
  const buildGate = gate(), searchGate = gate();
  let building = false, searching = false;
  await page.route("**/intent", route => json(route, { ...intent, kind: "unmapped" }));
  await page.route("**/build", async route => { building = true; await buildGate.waiting; await json(route, build); });
  await page.route("**/search?*", async route => { searching = true; await searchGate.waiting; await json(route, { results: [{ ...board, name: "Stale board" }] }); });
  await page.goto("/");
  await ask(page);
  await expect.poll(() => building && searching).toBe(true);
  await expect(page.locator(".intent-secondary-results")).not.toHaveAttribute("open", "");
  await answer(page).getByRole("button", { name: "Battery", exact: true }).click();
  await expect(result(page).getByRole("link", { name: "Fixture board" })).toBeVisible();
  const oldResponses = Promise.all([
    page.waitForResponse(response => response.url().endsWith("/build")),
    page.waitForResponse(response => response.url().includes("/search?")),
  ]);
  buildGate.release(); searchGate.release();
  await oldResponses;
  await expect(page.getByRole("status").first()).toHaveText("1 part match.");
  await expect(answer(page)).not.toContainText("Stale board");
  await expect(answer(page)).not.toContainText("a fixture project");
  await expect(answer(page)).toBeFocused();
});

test("empty run guide is an honest visible answer; malformed board rows become error UI", async ({ page }) => {
  await page.route("**/run/*", route => json(route, { ...guide, boards: [] }));
  await page.goto("/"); await ask(page);
  await expect(answer(page)).toContainText("No boards recorded for this firmware yet.");
  await page.route("**/intent", route => json(route, { ...intent, kind: "filters" }));
  await page.route("**/wizard", route => json(route, { results: [null] }));
  await ask(page, "boards");
  await expect(answer(page)).toContainText("The API did not answer");
});

test("a stalled guide times out visibly and re-enables submit", async ({ page }) => {
  await page.clock.install();
  await page.route("**/run/*", () => {});
  await page.goto("/"); await ask(page);
  await expect(answer(page)).toContainText("Finding recorded recipes");
  await page.clock.fastForward(21_000);
  await expect(answer(page)).toContainText("The request timed out");
  await expect(page.getByRole("button", { name: "Go", exact: true })).toBeEnabled();
});

test("home shelf really hides overflow from display and keyboard until revealed", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator(".example-card");
  await expect(cards).toHaveCount(49);
  await expect(page.locator(".example-card:visible")).toHaveCount(24);
  await cards.nth(24).evaluate(element => (element as HTMLElement).focus());
  await expect(cards.nth(24)).not.toBeFocused();
  await page.getByRole("button", { name: "Show more", exact: true }).click();
  await expect(cards.nth(24)).toBeFocused();
  await expect(page.locator(".example-card:visible")).toHaveCount(48);
  await page.getByRole("button", { name: "Show more", exact: true }).click();
  await expect(cards.nth(48)).toBeFocused();
  await expect(page.locator(".example-card:visible")).toHaveCount(49);
  await noOverflow(page);
});

test("all five sorts preserve the complete API order, reset the cap and preserve focus on final reveal", async ({ page, request }) => {
  await page.goto("/firmware");
  for (const option of SORT_OPTIONS) {
    if (option.value !== "popularity") await page.getByRole("navigation", { name: "Sort firmware" }).getByRole("link", { name: option.label, exact: true }).click();
    const data = await (await request.get(`http://127.0.0.1:8766/firmware?sort=${option.value}`)).json();
    const cards = page.locator(".results-list > .part-card");
    await expect(cards).toHaveCount(data.results.length);
    await expect(page.locator(".part-card:visible")).toHaveCount(24);
    expect(await cards.locator("h2 a").evaluateAll(links => links.map(link => link.getAttribute("href"))))
      .toEqual(data.results.map((fw: { id: string }) => `/firmware/${fw.id}`));
    await expect(cards.nth(24)).toBeHidden();
    expect(await cards.nth(24).ariaSnapshot()).toBe("");
    await cards.nth(24).locator("a").evaluate(element => (element as HTMLElement).focus());
    await expect(cards.nth(24).locator("a")).not.toBeFocused();
    await page.getByRole("button", { name: "Show more", exact: true }).click();
    await expect(page.locator(".part-card:visible")).toHaveCount(48);
    await expect(cards.nth(24).getByRole("link")).toBeFocused();
    await page.getByRole("button", { name: "Show more", exact: true }).click();
    await expect(page.locator(".part-card:visible")).toHaveCount(49);
    await expect(cards.nth(48).getByRole("link")).toBeFocused();
    await expect(page.getByRole("status")).toHaveText("Showing 49 of 49");
    await expect(page.getByRole("button", { name: "Show more", exact: true })).toHaveCount(0);
  }
  await expect(page.locator(".part-card h3")).toHaveCount(0);
  const unknown = page.locator('.part-card').filter({ has: page.locator('a[href="/firmware/fixture-48"]') });
  await expect(unknown.locator(".popularity-glance")).toHaveCount(0);
  await expect(page.getByText("GitHub repo · historical snapshot 2026-09-20", { exact: true }).first()).toBeVisible();
  await noOverflow(page);
});


test("the actual spec wizard can precede a guide without leaving stale results", async ({ page }) => {
  await page.goto("/");
  await page.locator(".spec-wizard-summary").click();
  await page.getByRole("button", { name: "Find parts", exact: true }).click();
  await expect(result(page).getByRole("link", { name: "Fixture board", exact: true })).toBeVisible();
  await ask(page);
  await expect(tracker(page)).toBeInViewport();
  await expect(result(page)).toHaveCount(0);
});

test("repository dates remain visible on the home shelf, index and firmware detail", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("GitHub repo · as of 2026-11-06 17:00 UTC", { exact: true }).first()).toBeVisible();
  await page.goto("/firmware");
  await expect(page.getByText("GitHub repo · as of 2026-11-06 17:00 UTC", { exact: true })).toBeVisible();
  await expect(page.getByText(/GitHub repo.*2026-10-01/)).toHaveCount(0);
  await page.locator('a[href="/firmware/fixture-00"]').click();
  await expect(page.getByRole("heading", { name: "Equal name", level: 1, exact: true })).toBeVisible();
  await expect(page.getByText("GitHub repo · as of 2026-11-06 17:00 UTC", { exact: true })).toBeVisible();
  await noOverflow(page);
});
