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
