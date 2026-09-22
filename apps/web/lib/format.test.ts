import { test } from "node:test";
import assert from "node:assert/strict";
import { boardsLabel, compactCount, firmwareMetaDescription, popularityGlance, readmeLanguageName } from "./format.ts";

test("maps known README source language codes to an English name", () => {
  assert.equal(readmeLanguageName("ja"), "Japanese");
  assert.equal(readmeLanguageName("zh"), "Chinese");
  assert.equal(readmeLanguageName("ko"), "Korean");
});

test("falls back to the raw code for an unmapped language", () => {
  assert.equal(readmeLanguageName("fr"), "fr");
});

test("boardsLabel is null for zero/missing boards, never '0 boards'", () => {
  assert.equal(boardsLabel(0), null);
  assert.equal(boardsLabel(null), null);
  assert.equal(boardsLabel(undefined), null);
});

test("boardsLabel singularizes exactly 1 board", () => {
  assert.equal(boardsLabel(1), "Runs on 1 board");
});

test("boardsLabel pluralizes 2+ boards", () => {
  assert.equal(boardsLabel(2), "Runs on 2 boards");
  assert.equal(boardsLabel(12), "Runs on 12 boards");
});

// firmwareMetaDescription() is shared by the firmware page's generateMetadata
// and structured-data.ts's SoftwareApplication node (which pulls in the rest
// of the app's "@/" alias graph and can't run under plain `node --test` — see
// faq-jsonld.test.ts) — this is the testable seam for both call sites.

test("uses the grounded summary as the description when present", () => {
  const description = firmwareMetaDescription({
    name: "ESPHome",
    category: "home",
    maintainer: "Open Home Foundation",
    socs: ["esp32", "esp32-s3"],
    summary: "ESPHome turns ESP32 boards into local-first smart-home devices with no cloud dependency.",
  });
  assert.equal(description, "ESPHome turns ESP32 boards into local-first smart-home devices with no cloud dependency.");
});

test("falls back to the category/maintainer/socs template when there is no summary", () => {
  const description = firmwareMetaDescription({
    name: "ESPHome",
    category: "home",
    maintainer: "Open Home Foundation",
    socs: ["esp32", "esp32-s3"],
    summary: undefined,
  });
  assert.equal(
    description,
    "ESPHome: Home firmware maintained by Open Home Foundation for esp32, esp32-s3 — see the boards it's verified to run on.",
  );
});

test("template omits the maintainer clause when there is none", () => {
  const description = firmwareMetaDescription({
    name: "Bruce",
    category: "pentest",
    maintainer: null,
    socs: [],
    summary: undefined,
  });
  assert.equal(description, "Bruce: Pentest firmware for ESP32 — see the boards it's verified to run on.");
});

// compactCount — SPEC-firmware-popularity.md §2/§6.5, boundaries 999/1000/999500/1000000.

test("compactCount renders exactly below 1000", () => {
  assert.equal(compactCount(0), "0");
  assert.equal(compactCount(999), "999");
});

test("compactCount switches to a trimmed k-suffix at 1000", () => {
  assert.equal(compactCount(1000), "1k");
});

test("compactCount rounds to one decimal, matching the spec's own examples", () => {
  assert.equal(compactCount(1234), "1.2k");
  assert.equal(compactCount(94567), "94.6k");
  assert.equal(compactCount(999500), "999.5k");
});

test("compactCount keeps the k-suffix past a million", () => {
  assert.equal(compactCount(1000000), "1000k");
});

// popularityGlance — SPEC-firmware-popularity.md §2.

test("popularityGlance formats both metrics, full numbers in the aria-label", () => {
  const glance = popularityGlance({ stars: 94567, forks: 12411 });
  assert.deepEqual(glance, {
    stars: "94.6k",
    forks: "12.4k",
    ariaLabel: "94,567 GitHub stars, 12,411 forks",
  });
});

test("popularityGlance puts as_of in a title tooltip, never inline", () => {
  const glance = popularityGlance({ stars: 94567, forks: 12411, as_of: "2026-09-14" });
  assert.equal(glance?.title, "stars as of 2026-09-14");
});

test("popularityGlance omits a null/absent metric silently, no zero", () => {
  const starsOnly = popularityGlance({ stars: 42, forks: null });
  assert.deepEqual(starsOnly, { stars: "42", ariaLabel: "42 GitHub stars" });

  const forksOnly = popularityGlance({ stars: undefined, forks: 7 });
  assert.deepEqual(forksOnly, { forks: "7", ariaLabel: "7 forks" });
});

test("popularityGlance is null when there is nothing to show", () => {
  assert.equal(popularityGlance(null), null);
  assert.equal(popularityGlance(undefined), null);
  assert.equal(popularityGlance({ stars: null, forks: null }), null);
});
