import { test } from "node:test";
import assert from "node:assert/strict";
import { detailRobots } from "./detail-robots.ts";

test("detailRobots leaves a healthy API result indexable", () => {
  assert.equal(detailRobots("ok"), undefined);
});

test("detailRobots noindexes a not_found result, unchanged from today", () => {
  assert.deepEqual(detailRobots("not_found"), { index: false });
});

test("detailRobots noindex,follow's an errored/cold API result so the id-only fallback shell never indexes", () => {
  assert.deepEqual(detailRobots("error"), { index: false, follow: true });
});
