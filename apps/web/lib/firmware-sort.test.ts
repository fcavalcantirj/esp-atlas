import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SORT, SORT_OPTIONS, firmwareLeadCopy, firmwareRobots, resolveSort, sortHref } from "./firmware-sort.ts";

test("SORT_OPTIONS carries the 5 v1 modes from SPEC-firmware-ordering.md §2, popularity first", () => {
  assert.deepEqual(
    SORT_OPTIONS.map((o) => o.value),
    ["popularity", "name", "name-desc", "forks", "boards"],
  );
});

test("resolveSort defaults to popularity when searchParams.sort is missing", () => {
  assert.equal(resolveSort(undefined), DEFAULT_SORT);
});

test("resolveSort clamps an unrecognized value to popularity, mirroring the API's own clamp", () => {
  assert.equal(resolveSort("stars-desc"), DEFAULT_SORT);
  assert.equal(resolveSort(""), DEFAULT_SORT);
});

test("resolveSort accepts every known mode", () => {
  for (const { value } of SORT_OPTIONS) {
    assert.equal(resolveSort(value), value);
  }
});

test("resolveSort takes the first value when Next hands a repeated query param", () => {
  assert.equal(resolveSort(["name", "forks"]), "name");
  assert.equal(resolveSort(["bogus", "forks"]), DEFAULT_SORT);
});

test("sortHref points the default mode at the bare canonical URL", () => {
  assert.equal(sortHref("popularity"), "/firmware");
});

test("sortHref carries every non-default mode as ?sort=", () => {
  assert.equal(sortHref("name"), "/firmware?sort=name");
  assert.equal(sortHref("name-desc"), "/firmware?sort=name-desc");
  assert.equal(sortHref("forks"), "/firmware?sort=forks");
  assert.equal(sortHref("boards"), "/firmware?sort=boards");
});

test("firmwareRobots leaves the default sort indexable when the API is up", () => {
  assert.equal(firmwareRobots("popularity", true), undefined);
});

test("firmwareRobots noindexes every non-default sort even when the API is up", () => {
  for (const mode of ["name", "name-desc", "forks", "boards"]) {
    assert.deepEqual(firmwareRobots(mode, true), { index: false, follow: true });
  }
});

test("firmwareRobots noindexes the default sort too when the API is cold/down", () => {
  assert.deepEqual(firmwareRobots("popularity", false), { index: false, follow: true });
});

test("firmwareLeadCopy for the default sort is byte-identical to the page's original copy", () => {
  assert.equal(
    firmwareLeadCopy(DEFAULT_SORT, 117),
    "117 flashable firmware projects, ranked by GitHub popularity — open one to see the boards it's verified to run on.",
  );
});

test("firmwareLeadCopy for an empty list is unchanged regardless of sort", () => {
  assert.equal(firmwareLeadCopy(DEFAULT_SORT, 0), "The firmware list could not be loaded right now — try again in a moment.");
  assert.equal(firmwareLeadCopy("boards", 0), "The firmware list could not be loaded right now — try again in a moment.");
});

test("firmwareLeadCopy states the active mode for a non-default sort", () => {
  assert.equal(
    firmwareLeadCopy("boards", 42),
    "42 flashable firmware projects, sorted by boards supported — open one to see the boards it's verified to run on.",
  );
});
