import test from "node:test";
import assert from "node:assert/strict";
import { atlasHref, atlasLens, sourceHref } from "./atlas-route.ts";

test("changing lenses retains the exact pair, recipe and free-text goal", () => {
  const url = atlasHref("part=m5cardputer&firmware=launcher&recipe=exact&goal=solar+pump&lens=map", { lens: "evidence" });
  const p = new URL(url, "https://example.test").searchParams;
  assert.equal(p.get("part"), "m5cardputer");
  assert.equal(p.get("firmware"), "launcher");
  assert.equal(p.get("recipe"), "exact");
  assert.equal(p.get("goal"), "solar pump");
  assert.equal(p.get("lens"), "evidence");
});
test("changing an endpoint can invalidate only the previous exact recipe", () => {
  const p = new URL(atlasHref("part=a&firmware=f&recipe=a__f&goal=A%26B", { part: "b", recipe: null }), "https://example.test").searchParams;
  assert.equal(p.get("part"), "b"); assert.equal(p.get("firmware"), "f");
  assert.equal(p.get("recipe"), null); assert.equal(p.get("goal"), "A&B");
});
test("unknown lens recovers to the map and unsafe source schemes are refused", () => {
  assert.equal(atlasLens("unknown"), "map"); assert.equal(atlasLens("evidence"), "evidence");
  assert.equal(sourceHref("javascript:alert(1)"), null);
  assert.equal(sourceHref("file:///local"), null);
  assert.equal(sourceHref("https://vendor.test/datasheet?q=a&b=c"), "https://vendor.test/datasheet?q=a&b=c");
});
