import { test } from "node:test";
import assert from "node:assert/strict";
import { firmwareMetaDescription, readmeLanguageName } from "./format.ts";

test("maps known README source language codes to an English name", () => {
  assert.equal(readmeLanguageName("ja"), "Japanese");
  assert.equal(readmeLanguageName("zh"), "Chinese");
  assert.equal(readmeLanguageName("ko"), "Korean");
});

test("falls back to the raw code for an unmapped language", () => {
  assert.equal(readmeLanguageName("fr"), "fr");
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
