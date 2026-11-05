import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { unscopedHumanReviewClaims } from "./public-copy.ts";

const WEB_ROOT = path.resolve(import.meta.dirname, "..");
const REPO_ROOT = path.resolve(WEB_ROOT, "../..");

// Everything that can reach esp-atlas.com as copy: pages, metadata, opengraph
// text, components, label tables, and the llms.txt the site serves.
function publicCopyFiles(): string[] {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) return walk(full);
      const isCopy = /\.(tsx?|json|md|txt)$/.test(name) && !name.endsWith(".test.ts") && name !== "public-copy.ts";
      return isCopy ? [full] : [];
    });
  return [...["app", "components", "lib"].flatMap((d) => walk(path.join(WEB_ROOT, d))), path.join(REPO_ROOT, "llms.txt")];
}

test("flags a blanket human-review claim", () => {
  assert.equal(unscopedHumanReviewClaims("A bot proposes what changed; humans review it; nothing lands").length, 1);
  assert.equal(unscopedHumanReviewClaims("Chewed daily by a bot, checked by humans, fixable by anyone.").length, 1);
  assert.equal(unscopedHumanReviewClaims("It opens pull requests, and a human decides.").length, 1);
});

test("allows a human-review claim scoped to what is actually held for review", () => {
  assert.deepEqual(unscopedHumanReviewClaims("New firmware entries and flashing claims are checked by humans before they publish."), []);
  assert.deepEqual(unscopedHumanReviewClaims("For a new recipe, a human decides."), []);
});

test("no public copy claims human review without scoping it", () => {
  const offenders = publicCopyFiles().flatMap((file) =>
    unscopedHumanReviewClaims(readFileSync(file, "utf8")).map((claim) => `${path.relative(REPO_ROOT, file)}: ${claim}`),
  );
  assert.deepEqual(offenders, []);
});
