import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { unscopedHumanReviewClaims } from "./public-copy.ts";
import { recipeCaveat, tierClaim } from "./flash-copy.ts";
import { boardsLabel, firmwareMetaDescription } from "./format.ts";

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

// Copy that claimed more evidence than a record carries. Board counts include
// unverified recipes and discovery leads, so none of these may come back.
const OVERCLAIMS = [
  "harvested from the project's build targets",
  "every board each one runs on",
  "if it isn't verified, it isn't stated",
  "verified to flash on",
  "verified to run on",
  "tests and an esp-target evidence gate",
  "runs on these boards",
  "runs on most boards",
  "sorted by boards supported",
];

/** Lower-cased, whitespace-collapsed, with JSX apostrophe entities and curly quotes read as "'". */
function normalizedCopy(text: string): string {
  return text.replace(/&apos;|&#39;|[‘’]/g, "'").replace(/\s+/g, " ").toLowerCase();
}

test("no public copy repeats an evidence overclaim", () => {
  const offenders = publicCopyFiles().flatMap((file) => {
    const copy = normalizedCopy(readFileSync(file, "utf8"));
    return OVERCLAIMS.filter((phrase) => copy.includes(phrase)).map((phrase) => `${path.relative(REPO_ROOT, file)}: ${phrase}`);
  });
  assert.deepEqual(offenders, []);
});

test("the unverified tier claim is source-neutral", () => {
  const claim = tierClaim("unverified", "M5Stack Cardputer");
  assert.match(claim, /^Unverified on M5Stack Cardputer/);
  assert.doesNotMatch(claim, /harvest|build target|build files/i);
  // Unverified recipes still cite where the pairing came from (build file, catalog): never deny that.
  assert.doesNotMatch(claim, /no (cited )?source/i);
});

test("the RuView Cardputer caveat renders at the flash action", () => {
  const recipeMd = readFileSync(path.join(REPO_ROOT, "data/recipes/m5cardputer__ruview/recipe.md"), "utf8");
  const quoted = recipeMd.match(/^notes: (".*")$/m);
  assert.ok(quoted, "m5cardputer__ruview must keep its notes caveat");
  const notes: string = JSON.parse(quoted[1]);
  assert.match(notes, /DISCOVERY ONLY/);

  assert.equal(recipeCaveat({ notes }), notes);
  assert.equal(recipeCaveat({ notes: null }), null);
  assert.equal(recipeCaveat({ notes: "   " }), null);

  const flashAction = readFileSync(path.join(WEB_ROOT, "components/flash/FlashAction.tsx"), "utf8");
  assert.match(flashAction, /const caveat = recipeCaveat\(recipe\);/);
  // Shown inside the panel before any rail (ready or handoff) renders, so no flash path skips it.
  const caveatAt = flashAction.indexOf('className="flash-caveat"');
  assert.ok(caveatAt > flashAction.indexOf('className="flash-panel"'), "caveat must render inside the flash panel");
  // Gated on the caveat alone, never on a phase, and ahead of the loading line.
  assert.match(flashAction, /\n {8}\{caveat && \(\s*<p className="flash-caveat"/);
  assert.ok(caveatAt < flashAction.indexOf('phase.kind === "loading"'), "caveat must render before any phase output");
  assert.ok(caveatAt < flashAction.indexOf('phase.kind === "ready" && ('), "caveat must render before the flash button");
  assert.ok(caveatAt < flashAction.indexOf('phase.kind === "handoff" && ('), "caveat must render before the handoff links");
});

test("a firmware board count is never described as verified", () => {
  const description = firmwareMetaDescription({ name: "RuView", category: "other", socs: ["esp32-s3"], boards: 3, summary: undefined });
  assert.doesNotMatch(description, /verified/i);
  assert.match(description, /3 boards/);
  // The card glance counts the same recipes: no "runs on" for an unverified lead.
  assert.equal(boardsLabel(3), "Recipes for 3 boards");
});

test("how-we-work separates Jr's evidence check, per-PR CI and owner review", () => {
  const page = normalizedCopy(readFileSync(path.join(WEB_ROOT, "app/how-we-work/page.tsx"), "utf8"));
  assert.ok(page.includes("before it proposes a new firmware"), "Jr's ESP-target evidence check must be its own stage");
  assert.ok(page.includes("on every pull request, ci validates"), "CI's per-PR checks must be their own stage");
  assert.ok(page.includes("held for a human maintainer"), "owner review must be its own stage");
});
