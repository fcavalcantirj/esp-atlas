import { test } from "node:test";
import assert from "node:assert/strict";
import { compatWithChip, firmwareForChip } from "./board-compat.ts";
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

// Real-ish fixtures: Cardputer ships esp32-s3; Marauder also cites plain
// esp32; Tasmota cites neither of those two (so a C3 detect dims it, never
// hides it as a false "runs").
const bruce = makeFirmware({ id: "bruce", name: "Bruce", socs: ["esp32-s3"], popularity: { stars: 1000 } });
const marauder = makeFirmware({
  id: "esp32marauder",
  name: "ESP32 Marauder",
  socs: ["esp32-s3", "esp32"],
  popularity: { stars: 500 },
});
const tasmota = makeFirmware({ id: "tasmota", name: "Tasmota", socs: ["esp32-c3"], popularity: { stars: 50 } });
const noSocsCited = makeFirmware({ id: "mystery", name: "Mystery Firmware", socs: [] });

test("compatWithChip is 'runs' when the firmware cites the detected chip family", () => {
  assert.equal(compatWithChip(bruce, "esp32-s3"), "runs");
  assert.equal(compatWithChip(marauder, "esp32"), "runs");
});

test("compatWithChip is 'no' when the firmware cites other chip families but not this one", () => {
  assert.equal(compatWithChip(bruce, "esp32-c3"), "no");
  assert.equal(compatWithChip(tasmota, "esp32-s3"), "no");
});

test("compatWithChip is 'unknown' when the firmware cites no socs at all -- never fabricated as 'runs' or 'no'", () => {
  assert.equal(compatWithChip(noSocsCited, "esp32-s3"), "unknown");
});

test("firmwareForChip keeps only firmware cited to run on the chip family", () => {
  const result = firmwareForChip([bruce, marauder, tasmota, noSocsCited], "esp32-s3");
  assert.deepEqual(
    result.map((f) => f.id),
    ["bruce", "esp32marauder"],
  );
});

test("firmwareForChip orders matches by cited stars descending", () => {
  const result = firmwareForChip([bruce, marauder], "esp32-s3");
  assert.deepEqual(
    result.map((f) => f.id),
    ["bruce", "esp32marauder"],
  );
});

test("firmwareForChip falls back to name A→Z when stars tie", () => {
  const a = makeFirmware({ id: "zeta", name: "Zeta", socs: ["esp32-s3"], popularity: { stars: 10 } });
  const b = makeFirmware({ id: "alpha", name: "Alpha", socs: ["esp32-s3"], popularity: { stars: 10 } });
  const result = firmwareForChip([a, b], "esp32-s3");
  assert.deepEqual(
    result.map((f) => f.id),
    ["alpha", "zeta"],
  );
});

test("firmwareForChip returns an empty list for a chip family nothing cites", () => {
  assert.deepEqual(firmwareForChip([bruce, marauder, tasmota], "esp8266"), []);
});

test("firmwareForChip does not mutate the input array", () => {
  const firmware = [marauder, bruce];
  const copy = [...firmware];
  firmwareForChip(firmware, "esp32-s3");
  assert.deepEqual(firmware, copy);
});
