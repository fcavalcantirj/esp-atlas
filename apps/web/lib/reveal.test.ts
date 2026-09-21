import { test } from "node:test";
import assert from "node:assert/strict";
import { PAGE_SIZE, initialReveal, revealCountLabel, revealMore } from "./reveal.ts";

test("PAGE_SIZE is 24 per SPEC-firmware-popularity.md D2", () => {
  assert.equal(PAGE_SIZE, 24);
});

test("initialReveal shows a full page when there's enough to fill it", () => {
  assert.equal(initialReveal(117), 24);
});

test("initialReveal never reveals more than exists", () => {
  assert.equal(initialReveal(10), 10);
  assert.equal(initialReveal(0), 0);
});

test("revealMore appends the next page", () => {
  assert.equal(revealMore(24, 117), 48);
});

test("revealMore caps at total on the final page", () => {
  assert.equal(revealMore(110, 117), 117);
  assert.equal(revealMore(117, 117), 117);
});

test("revealCountLabel reads 'Showing N of M'", () => {
  assert.equal(revealCountLabel(24, 117), "Showing 24 of 117");
  assert.equal(revealCountLabel(117, 117), "Showing 117 of 117");
});
