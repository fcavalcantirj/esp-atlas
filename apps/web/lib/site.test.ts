import { test } from "node:test";
import assert from "node:assert/strict";
import { SITE_URL, websiteSearchAction } from "./site.ts";

// websiteSearchAction() is the exact object spliced into structured-data.ts's
// website() as `potentialAction`. structured-data.ts itself pulls in the rest
// of the app's "@/" alias graph, which plain `node --test` can't resolve (see
// faq-jsonld.test.ts), so this is the testable seam for the WebSite
// SearchAction shape Google's sitelinks-searchbox rich result requires.

test("websiteSearchAction has the schema.org SearchAction shape for a sitelinks searchbox", () => {
  const action = websiteSearchAction();
  assert.equal(action["@type"], "SearchAction");
  assert.equal(action.target["@type"], "EntryPoint");
  assert.equal(action["query-input"], "required name=search_term_string");
});

test("the search target points at /wizard with a search_term_string template", () => {
  const action = websiteSearchAction();
  assert.equal(action.target.urlTemplate, `${SITE_URL}/wizard?q={search_term_string}`);
  assert.match(action.target.urlTemplate, /\{search_term_string\}/);
});

test("round-trips through JSON.stringify/parse unchanged", () => {
  const action = websiteSearchAction();
  const parsed = JSON.parse(JSON.stringify(action));
  assert.deepEqual(parsed, action);
});

test("live GA property is enabled only for production deployment", async () => {
  const importFresh = (suffix: string) => import("./site.ts?" + suffix);
  const original = {
    deployment: process.env.VERCEL_ENV,
    mode: process.env.NEXT_PUBLIC_GA_ENABLED,
    id: process.env.NEXT_PUBLIC_GA_ID,
  };
  try {
    delete process.env.NEXT_PUBLIC_GA_ENABLED;
    delete process.env.NEXT_PUBLIC_GA_ID;
    process.env.VERCEL_ENV = "preview";
    assert.equal((await importFresh("preview")).GA_ID, undefined);
    process.env.VERCEL_ENV = "production";
    assert.equal((await importFresh("production")).GA_ID, "G-66L7SDXKJZ");
    process.env.NEXT_PUBLIC_GA_ENABLED = "0";
    assert.equal((await importFresh("disabled")).GA_ID, undefined);
    process.env.VERCEL_ENV = "preview";
    process.env.NEXT_PUBLIC_GA_ENABLED = "1";
    process.env.NEXT_PUBLIC_GA_ID = "G-66L7SDXKJZ";
    assert.equal((await importFresh("preview-live-id")).GA_ID, undefined);
    process.env.NEXT_PUBLIC_GA_ID = "G-TESTATLAS1";
    assert.equal((await importFresh("preview-test-id")).GA_ID, "G-TESTATLAS1");
  } finally {
    for (const [key, value] of [
      ["VERCEL_ENV", original.deployment],
      ["NEXT_PUBLIC_GA_ENABLED", original.mode],
      ["NEXT_PUBLIC_GA_ID", original.id],
    ] as const) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
