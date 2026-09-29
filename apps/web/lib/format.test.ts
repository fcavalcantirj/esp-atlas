import { test } from "node:test";
import assert from "node:assert/strict";
import {
  boardsLabel,
  compactCount,
  firmwareMetaDescription,
  firmwareMetaTitle,
  partMetaDescription,
  partMetaTitle,
  popularityGlance,
  readmeLanguageName,
} from "./format.ts";

const TITLE_MAX = 60;
const DESCRIPTION_MAX = 155;

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

// firmwareMetaTitle()/firmwareMetaDescription() are shared by the firmware
// page's generateMetadata and structured-data.ts's SoftwareApplication node
// (which pulls in the rest of the app's "@/" alias graph and can't run under
// plain `node --test` — see faq-jsonld.test.ts) — this is the testable seam
// for both call sites. SPEC-serp-ctr.md: titles <=60 chars, descriptions
// <=155 chars, snippet leads with the boards/socs a firmware is verified to
// run on (the click-through lever), never fabricated.

test("firmware title leads with the name and states the boards + socs it's verified for", () => {
  const title = firmwareMetaTitle({ name: "ESPHome", socs: ["esp32", "esp32-s3"], boards: 12 });
  assert.equal(title, "ESPHome — flash guide for ESP32/ESP32-S3, 12 boards");
  assert.ok(title.length <= TITLE_MAX);
});

test("firmware title singularizes exactly 1 board", () => {
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32"], boards: 1 });
  assert.equal(title, "Bruce — flash guide for ESP32, 1 board");
});

test("firmware title falls back to socs when there's no boards count", () => {
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32"], boards: undefined });
  assert.equal(title, "Bruce — flash guide for ESP32");
});

test("firmware title falls back to a bare flash guide with neither socs nor boards", () => {
  const title = firmwareMetaTitle({ name: "Bruce", socs: [], boards: undefined });
  assert.equal(title, "Bruce — flash guide");
});

test("firmware title shortens a long name at a word boundary instead of dropping the benefit", () => {
  const title = firmwareMetaTitle({
    name: "Minigotchi-ESP32 StickC Plus 2 Ultra Deluxe Edition",
    socs: ["esp32"],
    boards: 3,
  });
  assert.ok(title.length <= TITLE_MAX, `expected <=${TITLE_MAX} chars, got ${title.length}: ${title}`);
  assert.ok(title.endsWith("… — flash guide"));
  const [truncatedName] = title.split(" — ");
  assert.ok(!truncatedName.slice(0, -1).endsWith(" "), "must not leave a trailing space before the ellipsis");
});

// seo_title: an optional per-firmware override (data/firmware/<id>/firmware.md
// `seo_title`) for the rare high-demand page where the generic "flash guide"
// formula buries the identity people actually search for. Absent/empty must
// stay byte-identical to the formula above -- this is an opt-in override for
// one record at a time, never a formula change (SPEC-serp-ctr.md).

test("firmware title returns a non-empty seo_title verbatim instead of the generic formula", () => {
  const title = firmwareMetaTitle({
    name: "PlatformIO",
    socs: ["esp32"],
    boards: 40,
    seo_title: "PlatformIO — ESP32 build system and debugger",
  });
  assert.equal(title, "PlatformIO — ESP32 build system and debugger");
  assert.ok(title.length <= TITLE_MAX);
});

test("firmware title clamps an over-long seo_title to TITLE_MAX at a word boundary", () => {
  const title = firmwareMetaTitle({
    name: "Cyber Controller",
    socs: ["esp32"],
    boards: 1,
    seo_title: "Cyber Controller — the definitive multi-firmware ESP32 flashing and provisioning dashboard for hobbyists",
  });
  assert.ok(title.length <= TITLE_MAX, `expected <=${TITLE_MAX} chars, got ${title.length}: ${title}`);
  assert.ok(title.startsWith("Cyber Controller"));
  assert.ok(title.endsWith("…"));
});

test("Bruce's own click-optimized seo_title overflows TITLE_MAX and is clamped at a word boundary", () => {
  // The exact editorial string set in data/firmware/bruce/firmware.md -- 65 chars,
  // 5 over TITLE_MAX, so the render-time clamp trims it rather than the author
  // having to hand-fit search copy to Google's SERP budget.
  const seoTitle = "Bruce — ESP32 / ESP32-S3 pentest firmware, flash guide and boards";
  assert.ok(seoTitle.length > TITLE_MAX);
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32", "esp32-s3", "esp32-c5"], boards: 11, seo_title: seoTitle });
  assert.equal(title, "Bruce — ESP32 / ESP32-S3 pentest firmware, flash guide and…");
  assert.ok(title.length <= TITLE_MAX);
});

test("firmware title ignores an empty seo_title and falls back to the generic formula", () => {
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32"], boards: 1, seo_title: "" });
  assert.equal(title, firmwareMetaTitle({ name: "Bruce", socs: ["esp32"], boards: 1 }));
});

test("firmware title with a missing seo_title is byte-identical to the generic formula", () => {
  const withUndefined = firmwareMetaTitle({ name: "ESPHome", socs: ["esp32", "esp32-s3"], boards: 12, seo_title: undefined });
  const withoutField = firmwareMetaTitle({ name: "ESPHome", socs: ["esp32", "esp32-s3"], boards: 12 });
  assert.equal(withUndefined, "ESPHome — flash guide for ESP32/ESP32-S3, 12 boards");
  assert.equal(withUndefined, withoutField);
});

test("uses the grounded summary as the description when it already fits", () => {
  const description = firmwareMetaDescription({
    name: "ESPHome",
    category: "home",
    socs: ["esp32", "esp32-s3"],
    boards: 12,
    summary: "ESPHome turns ESP32 boards into local-first smart-home devices with no cloud dependency.",
  });
  assert.equal(description, "ESPHome turns ESP32 boards into local-first smart-home devices with no cloud dependency.");
  assert.ok(description.length <= DESCRIPTION_MAX);
});

test("truncates an overlong summary at a word boundary rather than mid-word", () => {
  const longSummary =
    "Cyber Controller is a cross-platform application that lets you select, flash, and manage over 50 " +
    "firmware profiles for a variety of ESP32, ESP8266, Realtek, Flipper, and other boards, providing " +
    "serial monitoring and device-specific controls via a single desktop or web dashboard.";
  assert.ok(longSummary.length > DESCRIPTION_MAX);
  const description = firmwareMetaDescription({
    name: "cyber-controller",
    category: "pentest",
    socs: ["esp32"],
    boards: 1,
    summary: longSummary,
  });
  assert.ok(description.length <= DESCRIPTION_MAX, `expected <=${DESCRIPTION_MAX} chars, got ${description.length}`);
  assert.ok(description.endsWith("…"));
  assert.ok(longSummary.startsWith(description.slice(0, -1)), "truncation must not alter the kept prefix");
  assert.ok(!description.slice(0, -1).endsWith(" "), "must not leave a trailing space before the ellipsis");
});

test("falls back to the category/socs/boards template when there is no summary", () => {
  const description = firmwareMetaDescription({
    name: "ESPHome",
    category: "home",
    socs: ["esp32", "esp32-s3"],
    boards: 12,
    summary: undefined,
  });
  assert.equal(description, "ESPHome: Home firmware for ESP32, ESP32-S3. Verified to flash on 12 boards.");
  assert.ok(description.length <= DESCRIPTION_MAX);
});

test("template omits the boards clause when there is no verified board count", () => {
  const description = firmwareMetaDescription({
    name: "Bruce",
    category: "pentest",
    socs: [],
    boards: undefined,
    summary: undefined,
  });
  assert.equal(description, "Bruce: Pentest firmware for ESP32.");
});

// partMetaTitle()/partMetaDescription() -- same length rules, but the
// click-through lever is the concrete datasheet spec (Wi-Fi/BLE/802.15.4/USB)
// rather than boards.

test("part title leads with the name and states its concrete radio specs", () => {
  const title = partMetaTitle({
    name: "ESP32-C6",
    type: "soc",
    wifi_standard: "wifi-6",
    ble_version: "5.3",
    ieee802154: true,
    ieee802154_protocols: "zigbee-3.0,thread-1.3,matter",
    usb_native: true,
    form_factor: null,
  });
  assert.equal(title, "ESP32-C6 — Wi-Fi 6 + BLE 5.3 SoC specs");
  assert.ok(title.length <= TITLE_MAX);
});

test("part title falls back to the next real spec when there's no Wi-Fi/BLE", () => {
  const title = partMetaTitle({
    name: "M5StickC PLUS2",
    type: "board",
    wifi_standard: null,
    ble_version: null,
    ieee802154: false,
    ieee802154_protocols: null,
    usb_native: true,
    form_factor: null,
  });
  assert.equal(title, "M5StickC PLUS2 — native USB Board specs");
});

test("part title falls back to a bare type when the record cites no headline spec", () => {
  const title = partMetaTitle({
    name: "Generic Module",
    type: "module",
    wifi_standard: null,
    ble_version: null,
    ieee802154: false,
    ieee802154_protocols: null,
    usb_native: false,
    form_factor: null,
  });
  assert.equal(title, "Generic Module — Module specs");
});

test("part title shortens a long name at a word boundary instead of dropping the spec", () => {
  const title = partMetaTitle({
    name: "M5Stack Core2 v1.1 with AWS IoT EduKit Bundle and Extra Long Product Name",
    type: "board",
    wifi_standard: "wifi-4",
    ble_version: "4.2",
    ieee802154: false,
    ieee802154_protocols: null,
    usb_native: false,
    form_factor: null,
  });
  assert.ok(title.length <= TITLE_MAX, `expected <=${TITLE_MAX} chars, got ${title.length}: ${title}`);
  assert.ok(title.endsWith("… — Wi-Fi 4 + BLE 4.2 Board specs"));
});

const NO_SPEC_PART = {
  name: "Generic Module",
  type: "module",
  wifi_standard: null,
  ble_version: null,
  ieee802154: false,
  ieee802154_protocols: null,
  usb_native: false,
  form_factor: null,
};

test("part description uses the first body sentence when present", () => {
  const description = partMetaDescription(
    NO_SPEC_PART,
    "# ESP32-C6\n\nThe IoT all-rounder: **Wi-Fi 6 + BLE 5.3** in one chip, plus a low-power RISC-V core. The single-chip smart-home pick.",
  );
  assert.equal(description, "The IoT all-rounder: Wi-Fi 6 + BLE 5.3 in one chip, plus a low-power RISC-V core.");
  assert.ok(description.length <= DESCRIPTION_MAX);
});

test("part description truncates an overlong body sentence at a word boundary", () => {
  const longSentence =
    "This board is a datasheet-verified, cost-effective, widely-available development kit with an enormous " +
    "number of GPIO pins, dual-core processing, onboard Wi-Fi and Bluetooth radios, and a USB-C connector.";
  assert.ok(longSentence.length > DESCRIPTION_MAX);
  const description = partMetaDescription(NO_SPEC_PART, `${longSentence}\n`);
  assert.ok(description.length <= DESCRIPTION_MAX, `expected <=${DESCRIPTION_MAX} chars, got ${description.length}`);
  assert.ok(description.endsWith("…"));
});

test("part description falls back to the type/spec template when there is no body", () => {
  const description = partMetaDescription({
    name: "ESP32-C6",
    type: "soc",
    wifi_standard: "wifi-6",
    ble_version: "5.3",
    ieee802154: true,
    ieee802154_protocols: "zigbee-3.0,thread-1.3,matter",
    usb_native: true,
    form_factor: null,
  });
  assert.equal(description, "ESP32-C6: datasheet-verified SoC specs — Wi-Fi 6 + BLE 5.3 on esp-atlas.");
  assert.ok(description.length <= DESCRIPTION_MAX);
});

test("part description template omits the spec clause when the record cites none", () => {
  const description = partMetaDescription(NO_SPEC_PART);
  assert.equal(description, "Generic Module: datasheet-verified Module specs on esp-atlas.");
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
