import { test } from "node:test";
import assert from "node:assert/strict";
import { staticContentRoutes } from "./sitemap-routes.ts";

test("staticContentRoutes lists every static content page, including /submit", () => {
  const urls = staticContentRoutes("https://esp-atlas.com", undefined).map((e) => e.url);
  assert.deepEqual(urls, [
    "https://esp-atlas.com/",
    "https://esp-atlas.com/wizard",
    "https://esp-atlas.com/how-we-work",
    "https://esp-atlas.com/submit",
  ]);
});

test("staticContentRoutes dates / and /wizard from the catalog's newest date, not /how-we-work or /submit", () => {
  const entries = staticContentRoutes("https://esp-atlas.com", "2026-09-01");
  const byUrl = new Map(entries.map((e) => [e.url, e.lastModified]));
  assert.equal(byUrl.get("https://esp-atlas.com/"), "2026-09-01");
  assert.equal(byUrl.get("https://esp-atlas.com/wizard"), "2026-09-01");
  assert.equal(byUrl.get("https://esp-atlas.com/how-we-work"), undefined);
  assert.equal(byUrl.get("https://esp-atlas.com/submit"), undefined);
});
