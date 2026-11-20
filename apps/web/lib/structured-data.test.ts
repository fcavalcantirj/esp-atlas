// /firmware/<id> JSON-LD must not turn a recipe into a "runs on" claim: a
// recipe is a cited pairing at a trust tier, and an unverified one is not
// confirmed for its board. Exercises firmwareGraph() exactly as
// FirmwareDetailView calls it — the firmware, its recipes, and the parts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { firmwareGraph, partGraph } from "./structured-data.ts";
import type { Firmware, PartDetail, PartRecord, Recipe } from "./api.ts";

const CIRCUITPYTHON: Firmware = {
  id: "circuitpython",
  type: "firmware",
  name: "CircuitPython",
  url: "https://github.com/adafruit/circuitpython",
  category: "multi",
  maintainer: null,
  license: null,
  distribution: [],
  manifest_url: null,
  capabilities: [],
  socs: ["esp32"],
  sources: [],
  boards: 2,
};

function part(id: string, name: string): PartRecord {
  return {
    id,
    type: "board",
    name,
    vendor_or_brand: "m5stack",
    brand_name: "M5Stack",
    brand_url: null,
    wifi_standard: null,
    wifi_bands: null,
    ble_version: null,
    bt_classic: null,
    ieee802154: null,
    ieee802154_protocols: null,
    form_factor: null,
    price_tier: null,
    soc_ref: null,
    module_ref: null,
    usb_native: null,
    flash_mb: null,
    psram_mb: null,
    _path: "",
    sources: [],
  };
}

function recipe(board: string, status: string): Recipe {
  return {
    id: `${board}__circuitpython`,
    type: "recipe",
    board,
    firmware: "circuitpython",
    status,
    chip_family: "esp32",
    firmware_version: null,
    flash: null,
    verified_by: null,
    verified_at: null,
    notes: null,
    sources: [],
  };
}

const PARTS = [part("m5stack-core2", "Core2"), part("m5cardputer", "Cardputer")];

function boardList(recipes: Recipe[]) {
  const graph = firmwareGraph(CIRCUITPYTHON, recipes, PARTS)["@graph"] as Record<string, unknown>[];
  return graph.find((node) => node["@type"] === "ItemList") as
    | { name: string; numberOfItems: number; itemListElement: { name: string; description: string; url: string }[] }
    | undefined;
}

test("the board list is named for recipes, never 'runs on'", () => {
  const list = boardList([recipe("m5stack-core2", "unverified")]);
  assert.ok(list);
  assert.doesNotMatch(list.name, /runs? on/i);
  assert.match(list.name, /recipe/i);
  assert.doesNotMatch(JSON.stringify(list), /runs? on|known to run/i);
});

test("an unverified CircuitPython x Core2 item carries its own tier", () => {
  const list = boardList([recipe("m5stack-core2", "unverified")]);
  assert.ok(list);
  assert.equal(list.itemListElement.length, 1);
  assert.equal(list.itemListElement[0].name, "Core2");
  assert.match(list.itemListElement[0].description, /^Unverified on Core2/);
  assert.match(list.itemListElement[0].description, /not confirmed for this board/);
});

test("mixed tiers stay per item — no item inherits another's tier", () => {
  const list = boardList([recipe("m5stack-core2", "unverified"), recipe("m5cardputer", "known-good")]);
  assert.ok(list);
  assert.equal(list.numberOfItems, 2);
  const byName = new Map(list.itemListElement.map((item) => [item.name, item.description]));
  assert.match(byName.get("Core2") ?? "", /^Unverified on Core2/);
  assert.match(byName.get("Cardputer") ?? "", /^Known-good on Cardputer/);
});

test("a recipe whose board record is missing is left out, and no recipes means no list", () => {
  const list = boardList([recipe("not-a-board", "known-good"), recipe("m5cardputer", "known-good")]);
  assert.ok(list);
  assert.deepEqual(
    list.itemListElement.map((item) => item.name),
    ["Cardputer"],
  );
  assert.equal(boardList([]), undefined);
});


// GSC "Product snippets" (2026-11-14): every part page nested an `about` Product with no offers,
// review or aggregateRating, which Google reports as an invalid item. esp-atlas has no verified
// price or rating to cite (cite-or-omit), so a part page must never carry a Product node at all.
function hasType(node: unknown, type: string): boolean {
  if (Array.isArray(node)) return node.some((n) => hasType(n, type));
  if (!node || typeof node !== "object") return false;
  const t = (node as Record<string, unknown>)["@type"];
  if (t === type || (Array.isArray(t) && t.includes(type))) return true;
  return Object.values(node as Record<string, unknown>).some((v) => hasType(v, type));
}

function partDetail(type: string): PartDetail {
  return {
    id: "esp32-s3", type, name: "ESP32-S3", vendor_or_brand: "espressif", brand_name: "Espressif",
    sources: [{ field: "*", url: "https://documentation.espressif.com/esp32-s3_datasheet_en.pdf", verified: "2026-08-26" }],
    frontmatter: {}, body: "Dual-core SoC.", related: [], faq: [],
  } as unknown as PartDetail;
}

for (const type of ["soc", "module", "board"]) {
  test(`a ${type} page carries no Product node, so Google sees no invalid product snippet`, () => {
    assert.equal(hasType(partGraph(partDetail(type)), "Product"), false);
  });
}

test("the article still says what it is about, as a plain Thing", () => {
  const graph = partGraph(partDetail("soc"))["@graph"] as Record<string, unknown>[];
  const article = graph.find((n) => n["@type"] === "TechArticle") as { about?: Record<string, unknown> };
  assert.deepEqual(article.about, { "@type": "Thing", name: "ESP32-S3" });
});

// applicationCategory must be one of Google's application types, not the catalog's internal category
// (2026-11-18: live pages carried "multi", "pentest", "mesh"). The internal value stays visible as
// applicationSubCategory, so nothing the record says is lost.
test("firmware applicationCategory is a Google application type; the catalog category becomes the subcategory", () => {
  const cases: [string | null | undefined, string][] = [
    ["pentest", "SecurityApplication"], ["badusb", "SecurityApplication"], ["mesh", "CommunicationApplication"],
    ["home", "HomeApplication"], ["display", "MultimediaApplication"], ["multi", "UtilitiesApplication"],
    ["something-new", "UtilitiesApplication"], [undefined, "UtilitiesApplication"],
  ];
  for (const [category, expected] of cases) {
    const fw = { ...CIRCUITPYTHON, category } as Firmware;
    const app = (firmwareGraph(fw, [], PARTS)["@graph"] as Record<string, unknown>[]).find((n) => n["@type"] === "SoftwareApplication")!;
    assert.equal(app.applicationCategory, expected, String(category));
    if (category) assert.equal(app.applicationSubCategory, category);
    else assert.equal("applicationSubCategory" in app, false);
  }
});
