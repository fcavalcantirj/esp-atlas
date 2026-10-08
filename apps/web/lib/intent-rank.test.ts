import { test } from "node:test";
import assert from "node:assert/strict";
import { rankByIntent, scoreFirmware } from "./intent-rank.ts";
import type { Firmware } from "@/lib/api";

function makeFirmware(overrides: Partial<Firmware> & { id: string }): Firmware {
  return {
    type: "firmware",
    name: overrides.id,
    url: `https://github.com/example/${overrides.id}`,
    category: "multi",
    maintainer: null,
    license: null,
    distribution: [],
    manifest_url: null,
    capabilities: [],
    socs: [],
    sources: [],
    ...overrides,
  };
}

const bruce = makeFirmware({
  id: "bruce",
  name: "Bruce",
  summary: "A multi-tool firmware for Cardputer and other ESP32 boards — Wi-Fi, BLE and IR tools in one menu.",
  category: "pentest",
  capabilities: ["wifi", "ble", "ir"],
  socs: ["esp32-s3"],
  popularity: { stars: 1000 },
});

const marauder = makeFirmware({
  id: "esp32marauder",
  name: "ESP32 Marauder",
  summary: "A Wi-Fi and Bluetooth scanning/attack toolkit for the Cardputer and other ESP32-S3 boards.",
  category: "pentest",
  capabilities: ["wifi", "ble"],
  socs: ["esp32-s3", "esp32"],
  popularity: { stars: 500 },
});

const meshtastic = makeFirmware({
  id: "meshtastic",
  name: "Meshtastic",
  summary: "Long-range mesh messaging over LoRa for off-grid communication.",
  category: "mesh",
  capabilities: ["lora", "mesh"],
  socs: ["esp32", "esp32-s3"],
  popularity: { stars: 50 },
});

test("scoreFirmware is 0 for an empty query", () => {
  assert.equal(scoreFirmware(bruce, ""), 0);
  assert.equal(scoreFirmware(bruce, "   "), 0);
});

test("scoreFirmware is 0 when no query word appears anywhere in the firmware's fields", () => {
  assert.equal(scoreFirmware(bruce, "flipper subghz"), 0);
});

test("scoreFirmware weighs a name hit above a summary-only hit", () => {
  const nameHit = scoreFirmware(marauder, "marauder");
  const summaryOnly = scoreFirmware(bruce, "cardputer");
  assert.ok(nameHit > 0 && summaryOnly > 0);
  assert.ok(nameHit > summaryOnly);
});

test("scoreFirmware matches on a cited capability tag", () => {
  assert.ok(scoreFirmware(meshtastic, "mesh messaging") > 0);
  assert.equal(scoreFirmware(bruce, "mesh messaging"), 0);
});

test("scoreFirmware accumulates score across multiple matching words", () => {
  const oneWord = scoreFirmware(marauder, "wifi");
  const twoWords = scoreFirmware(marauder, "wifi marauder");
  assert.ok(twoWords > oneWord);
});

test("rankByIntent returns nothing for an empty query", () => {
  assert.deepEqual(rankByIntent([bruce, marauder, meshtastic], ""), []);
});

test("rankByIntent ranks matches highest-score first", () => {
  const result = rankByIntent([bruce, marauder, meshtastic], "marauder wifi");
  assert.deepEqual(
    result.map((f) => f.id),
    ["esp32marauder", "bruce"],
  );
});

test("rankByIntent excludes firmware that matches no query word", () => {
  const result = rankByIntent([bruce, marauder, meshtastic], "mesh");
  assert.deepEqual(
    result.map((f) => f.id),
    ["meshtastic"],
  );
});

test("rankByIntent ties break on cited stars descending, then name", () => {
  const a = makeFirmware({ id: "zeta", name: "Zeta Wifi Tool", capabilities: ["wifi"], popularity: { stars: 10 } });
  const b = makeFirmware({ id: "alpha", name: "Alpha Wifi Tool", capabilities: ["wifi"], popularity: { stars: 10 } });
  const c = makeFirmware({ id: "high", name: "High Wifi Tool", capabilities: ["wifi"], popularity: { stars: 90 } });
  const result = rankByIntent([a, b, c], "wifi tool");
  assert.deepEqual(
    result.map((f) => f.id),
    ["high", "alpha", "zeta"],
  );
});

test("rankByIntent caps results to the given limit", () => {
  const firmware = Array.from({ length: 10 }, (_, i) =>
    makeFirmware({ id: `fw-${i}`, name: `Wifi Tool ${i}`, capabilities: ["wifi"], popularity: { stars: 100 - i } }),
  );
  const result = rankByIntent(firmware, "wifi", 3);
  assert.equal(result.length, 3);
  assert.deepEqual(
    result.map((f) => f.id),
    ["fw-0", "fw-1", "fw-2"],
  );
});

test("rankByIntent defaults to a limit of 6", () => {
  const firmware = Array.from({ length: 10 }, (_, i) =>
    makeFirmware({ id: `fw-${i}`, name: `Wifi Tool ${i}`, capabilities: ["wifi"], popularity: { stars: 100 - i } }),
  );
  assert.equal(rankByIntent(firmware, "wifi").length, 6);
});

test("rankByIntent does not mutate the input array", () => {
  const firmware = [marauder, bruce, meshtastic];
  const copy = [...firmware];
  rankByIntent(firmware, "wifi");
  assert.deepEqual(firmware, copy);
});
