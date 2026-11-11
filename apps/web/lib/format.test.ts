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
import { firmwareForChip } from "./chip-firmware.ts";

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
  assert.equal(boardsLabel(1), "Recipes for 1 board");
});

test("boardsLabel pluralizes 2+ boards", () => {
  assert.equal(boardsLabel(2), "Recipes for 2 boards");
  assert.equal(boardsLabel(12), "Recipes for 12 boards");
});

// firmwareMetaTitle()/firmwareMetaDescription() are shared by the firmware
// page's generateMetadata and structured-data.ts's SoftwareApplication node
// (which pulls in the rest of the app's "@/" alias graph and can't run under
// plain `node --test` — see faq-jsonld.test.ts) — this is the testable seam
// for both call sites. SPEC-serp-ctr.md: titles <=60 chars, descriptions
// <=155 chars, snippet leads with the boards a firmware has recipes for and
// the socs it targets (the click-through lever), never fabricated.

test("firmware title leads with the name and states its recipe board count + socs", () => {
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

test("an over-long seo_title (65 chars, the kind that used to ship for Bruce) still clamps at a word boundary", () => {
  // Historical fixture, not the live data/firmware/bruce/firmware.md value anymore --
  // 65 chars, 5 over TITLE_MAX, kept as a clamp-boundary regression guard so the
  // truncation path stays exercised even now that Bruce's own seo_title fits.
  const seoTitle = "Bruce — ESP32 / ESP32-S3 pentest firmware, flash guide and boards";
  assert.ok(seoTitle.length > TITLE_MAX);
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32", "esp32-s3", "esp32-c5"], boards: 11, seo_title: seoTitle });
  assert.equal(title, "Bruce — ESP32 / ESP32-S3 pentest firmware, flash guide and…");
  assert.ok(title.length <= TITLE_MAX);
});

test("Bruce's live seo_title (data/firmware/bruce/firmware.md) fits TITLE_MAX and renders verbatim, unclamped", () => {
  // Regression guard for the SERP-title truncation bug: this string must stay
  // <=TITLE_MAX so firmwareMetaTitle never has to clamp it (which would cut the
  // live title mid-phrase with an ellipsis). If a future edit to that file's
  // seo_title grows past TITLE_MAX again, this test catches it before it ships.
  const seoTitle = "Bruce — ESP32/ESP32-S3 pentest firmware & flash guide";
  assert.ok(seoTitle.length <= TITLE_MAX, `expected <=${TITLE_MAX} chars, got ${seoTitle.length}`);
  const title = firmwareMetaTitle({ name: "Bruce", socs: ["esp32", "esp32-s3", "esp32-c5"], boards: 11, seo_title: seoTitle });
  assert.equal(title, seoTitle);
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
  assert.equal(description, "ESPHome: Home firmware for ESP32, ESP32-S3. Recipes for 12 boards, each labelled with its trust tier.");
  assert.ok(description.length <= DESCRIPTION_MAX);
});

test("template omits the boards clause when there is no recipe board count", () => {
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

test("part title preserves a long board name and shortens generic specs", () => {
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
  assert.ok(title.startsWith("M5Stack Core2 v1.1 with AWS IoT EduKit Bundle and Extra Long Product Name"));
  assert.ok(title.endsWith(" — Board specs"));
});

// pinout in the title: search-intent word ("lolin s2 mini pinout") that Google
// Search Console shows earning impressions at 0% CTR on generic titles
// (SPEC-serp-ctr.md). Cite-or-omit: only parts whose frontmatter carries a real
// images.pinout diagram (rendered by BoardImage.tsx) may claim the word.

test("part title includes 'pinout' when the part has a pinout diagram (data/boards/espressif/esp32-s3-devkitm-1/board.md images.pinout)", () => {
  const title = partMetaTitle(
    {
      name: "ESP32-S3-DevKitM-1",
      type: "board",
      wifi_standard: "wifi-4",
      ble_version: "5",
      ieee802154: false,
      ieee802154_protocols: null,
      usb_native: false,
      form_factor: "devkit",
    },
    true,
  );
  assert.ok(title.includes("pinout"), `expected title to include "pinout": ${title}`);
  assert.ok(title.length <= TITLE_MAX);
});

test("part title is unchanged and omits 'pinout' when the part has no pinout diagram (data/socs/esp32-c3/chip.md carries no images)", () => {
  const soc = {
    name: "ESP32-C3",
    type: "soc",
    wifi_standard: "wifi-4",
    ble_version: "5",
    ieee802154: false,
    ieee802154_protocols: null,
    usb_native: true,
    form_factor: null,
  };
  const title = partMetaTitle(soc, false);
  assert.equal(title, "ESP32-C3 — Wi-Fi 4 + BLE 5 SoC specs");
  assert.ok(!title.includes("pinout"));
  assert.equal(title, partMetaTitle(soc));
});

test("a long name plus pinout preserves exact identity (data/boards/m5stack/m5stack-core2/board.md images.pinout)", () => {
  const title = partMetaTitle(
    {
      name: "Core2 v1.1 with AWS IoT EduKit Bundle and Extra Long Product Name",
      type: "board",
      wifi_standard: "wifi-4",
      ble_version: "4.2",
      ieee802154: false,
      ieee802154_protocols: null,
      usb_native: false,
      form_factor: "m5-core",
    },
    true,
  );
  assert.ok(title.startsWith("Core2 v1.1 with AWS IoT EduKit Bundle and Extra Long Product Name"));
  assert.ok(title.includes("pinout"), `expected title to include "pinout": ${title}`);
});

test("all 17 board names in the November audit collision groups remain distinct", () => {
  const names = [
    "Adafruit ESP32-S3 Feather (4MB Flash 2MB PSRAM)",
    "Adafruit ESP32-S3 Feather (8MB Flash No PSRAM)",
    "Adafruit ESP32-S3 Reverse TFT Feather (4MB Flash 2MB PSRAM)",
    "Adafruit QT Py ESP32-C3 WiFi Dev Board with STEMMA QT",
    "Adafruit QT Py ESP32-S3 WiFi Dev Board with STEMMA QT (8 MB Flash No PSRAM)",
    "Adafruit QT Py ESP32-S3 WiFi Dev Board with STEMMA QT (8MB Flash No PSRAM)",
    "Adafruit Sparkle Motion",
    "Adafruit Sparkle Motion Mini",
    "Adafruit Sparkle Motion Stick",
    "DFRobot FireBeetle 2 ESP32-E",
    "DFRobot FireBeetle ESP32",
    "ESP32-S3 Display FNK0104A",
    "ESP32-S3 Display FNK0104B",
    "ESP32-S3 Display FNK0104S",
    "Seeed Studio XIAO ESP32C3",
    "Seeed Studio XIAO ESP32S3",
    "Seeed Studio XIAO ESP32S3 Sense",
  ];
  const titles = names.map((name) => partMetaTitle({
    name, type: "board", wifi_standard: "wifi-4", ble_version: "5", ieee802154: false,
    ieee802154_protocols: null, usb_native: false, form_factor: null,
  }, true));
  assert.equal(new Set(titles).size, 17);
  titles.forEach((title, i) => assert.ok(title.startsWith(names[i]), title));
});

// The chip hub (SPEC-serp-ctr.md §4): a SoC with related parts is the hub for
// "<chip> specs, boards and firmware", so its title says so when it fits.

const ESP32_C6 = {
  name: "ESP32-C6",
  type: "soc",
  wifi_standard: "wifi-6",
  ble_version: "5.3",
  ieee802154: true,
  ieee802154_protocols: "zigbee-3.0,thread-1.3,matter",
  usb_native: true,
  form_factor: null,
};

test("a SoC with related parts uses the hub benefit 'SoC: specs, boards, firmware'", () => {
  const title = partMetaTitle(ESP32_C6, false, true);
  assert.equal(title, "ESP32-C6 — Wi-Fi 6 + BLE 5.3 SoC: specs, boards, firmware");
  assert.ok(title.length <= TITLE_MAX);
});

test("a SoC without related parts keeps today's 'SoC specs' title byte-identically", () => {
  assert.equal(partMetaTitle(ESP32_C6, false, false), "ESP32-C6 — Wi-Fi 6 + BLE 5.3 SoC specs");
  assert.equal(partMetaTitle(ESP32_C6, false, false), partMetaTitle(ESP32_C6));
});

test("the hub title is used when it is exactly TITLE_MAX chars", () => {
  const soc = { ...ESP32_C6, name: "ESP32-S3-PICO", wifi_standard: "wifi-4", ble_version: "5" };
  const title = partMetaTitle(soc, false, true);
  assert.equal(title, "ESP32-S3-PICO — Wi-Fi 4 + BLE 5 SoC: specs, boards, firmware");
  assert.equal(title.length, TITLE_MAX);
});

test("the hub title falls back to today's 'SoC specs' when it would exceed TITLE_MAX", () => {
  const soc = { ...ESP32_C6, name: "ESP32-S3-PICO-1", wifi_standard: "wifi-4", ble_version: "5" };
  assert.equal(partMetaTitle(soc, false, true), "ESP32-S3-PICO-1 — Wi-Fi 4 + BLE 5 SoC specs");
});

test("'pinout' counts against the hub title's cap", () => {
  const soc = { ...ESP32_C6, name: "ESP32-C3", wifi_standard: "wifi-4", ble_version: "5" };
  assert.equal(partMetaTitle(soc, true, true), "ESP32-C3 pinout — Wi-Fi 4 + BLE 5 SoC specs");
});

test("hasRelated never changes a non-SoC title", () => {
  const board = { ...ESP32_C6, name: "ESP32-C6-DevKitC-1", type: "board" };
  assert.equal(partMetaTitle(board, false, true), partMetaTitle(board, false, false));
});

// Part seo_title (SPEC-serp-ctr.md §3): the firmwareMetaTitle semantics exactly.

test("part title returns a non-empty seo_title verbatim, over hub and pinout", () => {
  const seoTitle = "ESP32-C6 specs, boards and firmware — Wi-Fi 6, Thread";
  assert.equal(partMetaTitle({ ...ESP32_C6, seo_title: seoTitle }, true, true), seoTitle);
});

test("part title clamps an over-long seo_title to TITLE_MAX at a word boundary", () => {
  const seoTitle = "ESP32-C6 — every Wi-Fi 6, Thread and Zigbee board, module and firmware in one place";
  const title = partMetaTitle({ ...ESP32_C6, seo_title: seoTitle });
  assert.ok(title.length <= TITLE_MAX, `${title.length}: ${title}`);
  assert.ok(title.endsWith("…"));
  const kept = title.slice(0, -1);
  assert.ok(seoTitle.startsWith(kept));
  assert.equal(seoTitle[kept.length], " ", "cut must land on a word boundary");
});

test("part title with an empty or missing seo_title is byte-identical to the formula", () => {
  for (const [hasPinout, hasRelated] of [[false, false], [true, false], [false, true], [true, true]]) {
    const formula = partMetaTitle(ESP32_C6, hasPinout, hasRelated);
    assert.equal(partMetaTitle({ ...ESP32_C6, seo_title: "" }, hasPinout, hasRelated), formula);
    assert.equal(partMetaTitle({ ...ESP32_C6, seo_title: undefined }, hasPinout, hasRelated), formula);
    assert.equal(partMetaTitle({ ...ESP32_C6, seo_title: null }, hasPinout, hasRelated), formula);
  }
});

// Firmware for a chip (SPEC-serp-ctr.md §4): every firmware whose `socs`
// names the chip, in index order; none means the hub section renders nothing.

const fw = (id: string, socs: string[]) => ({ id, name: id, category: "multi", socs });

test("firmwareForChip keeps only firmware whose socs name the chip, in index order", () => {
  const list = [fw("bruce", ["esp32", "esp32-c6"]), fw("tasmota", ["esp32"]), fw("esphome", ["esp32-c6", "esp32-s3"])];
  assert.deepEqual(firmwareForChip(list, "esp32-c6").map((f) => f.id), ["bruce", "esphome"]);
});

test("firmwareForChip matches the soc id exactly, not by prefix", () => {
  const list = [fw("a", ["esp32-c61"]), fw("b", ["esp32"])];
  assert.deepEqual(firmwareForChip(list, "esp32-c6"), []);
});

test("firmwareForChip is empty when no firmware names the chip (n = 0 renders nothing)", () => {
  assert.deepEqual(firmwareForChip([fw("tasmota", ["esp32"])], "esp32-p4"), []);
  assert.deepEqual(firmwareForChip([], "esp32-c6"), []);
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
    ariaLabel: "94,567 GitHub stars, 12,411 forks. GitHub repo · date not recorded",
    title: "94,567 GitHub stars, 12,411 forks. GitHub repo · date not recorded",
    scope: "GitHub repo · date not recorded",
  });
});

test("popularityGlance labels legacy dates as historical snapshots", () => {
  const glance = popularityGlance({ stars: 94567, forks: 12411, as_of: "2026-09-14" });
  assert.equal(glance?.scope, "GitHub repo · historical snapshot 2026-09-14");
});

test("popularityGlance omits a null/absent metric silently, no zero", () => {
  const starsOnly = popularityGlance({ stars: 42, forks: null });
  assert.equal(starsOnly?.stars, "42");
  assert.equal(starsOnly?.forks, undefined);

  const forksOnly = popularityGlance({ stars: undefined, forks: 7 });
  assert.equal(forksOnly?.forks, "7");
  assert.equal(forksOnly?.stars, undefined);
});

test("popularityGlance is null when there is nothing to show", () => {
  assert.equal(popularityGlance(null), null);
  assert.equal(popularityGlance(undefined), null);
  assert.equal(popularityGlance({ stars: null, forks: null }), null);
});


test("GitHub-specific date takes precedence over the legacy snapshot", () => {
  const glance = popularityGlance({ stars: 0, forks: 7, as_of: "2026-09-14", github_as_of: "2026-11-06T17:00:00Z" });
  assert.equal(glance?.scope, "GitHub repo · as of 2026-11-06 17:00 UTC");
  assert.equal(glance?.stars, "0");
  assert.ok(glance?.ariaLabel.includes("0 GitHub stars, 7 forks"));
});

test("GitHub timestamps display in UTC regardless of their encoded offset", () => {
  assert.equal(popularityGlance({ stars: 7, github_as_of: "2026-11-06T15:30:20-03:00" })?.scope,
    "GitHub repo · as of 2026-11-06 18:30 UTC");
});
