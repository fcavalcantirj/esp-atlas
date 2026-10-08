import { test } from "node:test";
import assert from "node:assert/strict";
import { countCapabilities, WALL_CAPABILITIES } from "./capability-facets.ts";
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

const bruce = makeFirmware({ id: "bruce", capabilities: ["wifi", "ble", "ir"] });
const marauder = makeFirmware({ id: "esp32marauder", capabilities: ["wifi", "ble"] });
const meshtastic = makeFirmware({ id: "meshtastic", capabilities: ["lora", "mesh"] });
const cardputerOs = makeFirmware({ id: "cardputer-os", capabilities: [] });

test("countCapabilities counts how many firmware cite each capability", () => {
  const result = countCapabilities([bruce, marauder, meshtastic, cardputerOs]);
  const byValue = new Map(result.map((f) => [f.value, f.count]));
  assert.equal(byValue.get("wifi"), 2);
  assert.equal(byValue.get("ble"), 2);
  assert.equal(byValue.get("ir"), 1);
  assert.equal(byValue.get("lora"), 1);
  assert.equal(byValue.get("mesh"), 1);
});

test("countCapabilities omits a capability nothing cites -- the filter rail never offers a dead chip", () => {
  const result = countCapabilities([bruce]);
  assert.equal(result.some((f) => f.value === "lora"), false);
  assert.equal(result.some((f) => f.value === "sub-ghz"), false);
});

test("countCapabilities returns an empty list when no firmware cites any watched capability", () => {
  assert.deepEqual(countCapabilities([cardputerOs]), []);
});

test("countCapabilities only ever reports the capabilities it was asked to watch", () => {
  const withExtra = makeFirmware({ id: "extra", capabilities: ["wifi", "zigbee"] });
  const result = countCapabilities([withExtra]);
  assert.deepEqual(result.map((f) => f.value).sort(), ["wifi"]);
});

test("countCapabilities preserves the watched-list order among reported facets", () => {
  const result = countCapabilities([bruce, marauder, meshtastic]);
  const order = result.map((f) => f.value);
  const expectedOrder = WALL_CAPABILITIES.filter((cap) => order.includes(cap));
  assert.deepEqual(order, expectedOrder);
});

test("WALL_CAPABILITIES carries the 8 capability chips from the design (wifi/ble/lora/mesh/badusb/ir/gps/sub-ghz)", () => {
  assert.deepEqual(WALL_CAPABILITIES, ["wifi", "ble", "lora", "mesh", "badusb", "ir", "gps", "sub-ghz"]);
});

test("countCapabilities accepts a custom capability list", () => {
  const result = countCapabilities([bruce], ["wifi", "ir"]);
  assert.deepEqual(
    result.map((f) => f.value),
    ["wifi", "ir"],
  );
});
