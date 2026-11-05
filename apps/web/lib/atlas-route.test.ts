import test from "node:test";
import assert from "node:assert/strict";
import { atlasHref, atlasLens, recipeSourceHref, sourceHref } from "./atlas-route.ts";
import type { Recipe, SourceEntry } from "./api.ts";

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

const citation = (url: string, field = "*"): SourceEntry => ({ url, field, verified: "2026-11-05" });
const broken: Pick<Recipe, "status" | "flash"> = {
  status: "broken",
  flash: { method: "release-bin", bin_url: "https://vendor.test/download?id=broken", manifest_url: "https://vendor.test/install?id=broken", offset: null, env: null, partition: null },
};
test("broken recipe citations cannot hand off recorded binaries or project manifests", () => {
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/download?id=broken#historical")), null);
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/install?id=broken")), null);
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/other-artifact", "flash.bin_url")), null);
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/other-manifest", "flash.manifest_url")), null);
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/flasher", "distribution")), null);
});
test("broken recipe evidence retains documentation while direct artifact citations stay inert", () => {
  const withoutFlash = { status: "broken", flash: null };
  assert.equal(recipeSourceHref(withoutFlash, citation("https://vendor.test/history.BIN?download=1")), null);
  assert.equal(recipeSourceHref(withoutFlash, citation("https://vendor.test/firmware.uf2")), null);
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/wiki/board")), "https://vendor.test/wiki/board");
  assert.equal(recipeSourceHref(broken, citation("https://vendor.test/boot-notes", "flash.offset")), "https://vendor.test/boot-notes");
});
test("other recipe tiers retain cited links without relaxing source scheme validation", () => {
  for (const status of ["known-good", "declared", "reported", "unverified", "future-tier"]) {
    const recipe = { ...broken, status };
    assert.equal(recipeSourceHref(recipe, citation("https://vendor.test/firmware.bin", "flash.bin_url")), "https://vendor.test/firmware.bin");
    assert.equal(recipeSourceHref(recipe, citation("javascript:alert(1)")), null);
  }
});
