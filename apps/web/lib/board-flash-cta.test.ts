import { test } from "node:test";
import assert from "node:assert/strict";
import { boardFlashCtaLabel, boardFlashCtaParams, highestTrustTier, shouldShowBoardFlashCta } from "./board-flash-cta.ts";

const row = (status: string) => ({ recipe: { status } });

test("shows the CTA for a board with at least one firmware recipe row", () => {
  assert.equal(shouldShowBoardFlashCta("board", [row("known-good")]), true);
});

test("does not show the CTA for a non-board part, even with rows", () => {
  assert.equal(shouldShowBoardFlashCta("soc", [row("known-good")]), false);
  assert.equal(shouldShowBoardFlashCta("module", [row("known-good")]), false);
});

test("does not show the CTA when rows is null (not yet fetched / not a board page)", () => {
  assert.equal(shouldShowBoardFlashCta("board", null), false);
});

test("does not show the CTA for a board with zero firmware rows", () => {
  assert.equal(shouldShowBoardFlashCta("board", []), false);
});

test("highestTrustTier prefers known-good over every other tier present", () => {
  assert.equal(highestTrustTier([row("broken"), row("unverified"), row("known-good"), row("reported")]), "known-good");
});

test("highestTrustTier falls back down the tier order when known-good is absent", () => {
  assert.equal(highestTrustTier([row("broken"), row("reported")]), "reported");
  assert.equal(highestTrustTier([row("broken"), row("unverified")]), "unverified");
  assert.equal(highestTrustTier([row("broken")]), "broken");
});

test("highestTrustTier is null for no rows", () => {
  assert.equal(highestTrustTier([]), null);
});

test("highestTrustTier ignores an unrecognized status when a known tier is also present", () => {
  assert.equal(highestTrustTier([row("weird"), row("reported")]), "reported");
});

test("boardFlashCtaLabel states the count and the highest trust tier, singularized at 1", () => {
  assert.equal(boardFlashCtaLabel([row("known-good")]), "1 firmware option · Known good");
  assert.equal(boardFlashCtaLabel([row("known-good"), row("reported")]), "2 firmware options · Known good");
  assert.equal(boardFlashCtaLabel([row("broken"), row("broken")]), "2 firmware options · Broken");
});

test("boardFlashCtaParams carries the board's part_id plus the count and tier for analytics", () => {
  const params = boardFlashCtaParams("m5stack-core2", [row("known-good"), row("reported")]);
  assert.equal(params.part_id, "m5stack-core2");
  assert.equal(params.count, 2);
  assert.equal(params.tier, "known-good");
});
