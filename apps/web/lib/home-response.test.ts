import { test } from "node:test";
import assert from "node:assert/strict";
import { assertBuildGuideResponse, assertIntentResponse, assertPartResults, assertRunGuideResponse } from "./home-response.ts";

test("malformed success payloads are rejected instead of breaking answer rendering", () => {
  for (const value of [null, [], {}, "ok", { detail: "provider unavailable" }]) {
    assert.throws(() => assertIntentResponse(value));
    assert.throws(() => assertRunGuideResponse(value, "tracker"));
    assert.throws(() => assertBuildGuideResponse(value));
  }
});
test("an empty but valid guide stays an honest empty answer", () => {
  assertRunGuideResponse({ firmware: "tracker", summary: "No boards recorded", grounded: false, requires: [], not_required: [], boards: [] }, "tracker");
  assertBuildGuideResponse({ goal: "a project", needs: [], boards: [], firmware: null });
});
test("a guide for a different firmware cannot be presented as this query's response", () => {
  assert.throws(() => assertRunGuideResponse({ firmware: "other", summary: "", grounded: true, requires: [], not_required: [], boards: [] }, "tracker"));
});
test("nested malformed fields are caught before mapping or rendering", () => {
  assert.throws(() => assertIntentResponse({ kind: "filters", filters: [], understood: [], unmapped: [], cached: false }));
  assert.throws(() => assertRunGuideResponse({ firmware: "tracker", summary: "", grounded: true, requires: [null], not_required: [], boards: [] }, "tracker"));
  assert.throws(() => assertBuildGuideResponse({ goal: "a project", needs: [], boards: [{ board_id: "board", board_name: "Board", why: {} }] }));
});

test("malformed board result rows become a recoverable error, while an empty list is valid", () => {
  for (const payload of [{ results: null }, { results: [null] }, { results: [{ id: "board", name: {} }] },
    { results: [{ id: "board", name: "Board", type: "board", reasons: null }] }]) {
    assert.throws(() => assertPartResults(payload));
  }
  assertPartResults({ results: [] });
});
