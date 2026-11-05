import { test } from "node:test";
import assert from "node:assert/strict";
import { staticContentRoutes } from "./sitemap-routes.ts";

test("staticContentRoutes lists every static content page, including /submit", () => {
  const urls = staticContentRoutes("https://esp-atlas.com").map((e) => e.url);
  assert.deepEqual(urls, [
    "https://esp-atlas.com/",
    "https://esp-atlas.com/wizard",
    "https://esp-atlas.com/how-we-work",
    "https://esp-atlas.com/submit",
  ]);
});

test("staticContentRoutes omits unverified content change dates", () => {
  const entries = staticContentRoutes("https://esp-atlas.com");
  assert.ok(entries.every((entry) => entry.lastModified === undefined));
});
