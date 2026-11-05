import { test } from "node:test";
import assert from "node:assert/strict";
import type { Firmware, PartRecord, Recipe } from "./api.ts";
import { buildAtlasModel, exactRecipe, type AtlasCatalog } from "./atlas-model.ts";

function part(id: string, type: string, soc_ref: string | null, module_ref: string | null = null): PartRecord {
  return {
    id, type, name: id, soc_ref, module_ref, vendor_or_brand: "test", brand_name: "Test", brand_url: null,
    wifi_standard: null, wifi_bands: null, ble_version: null, bt_classic: false, ieee802154: null,
    ieee802154_protocols: null, form_factor: null, price_tier: null, usb_native: null,
    flash_mb: null, psram_mb: 0, _path: `data/${id}.md`, sources: [],
  };
}

function firmware(id: string): Firmware {
  return { id, type: "firmware", name: id, url: "https://example.test/project", category: "multi",
    maintainer: null, license: null, distribution: [], manifest_url: null, capabilities: [], socs: [], sources: [] };
}

function recipe(id: string, board: string, target: string, status = "unverified"): Recipe {
  return { id, type: "recipe", board, firmware: target, status, chip_family: "chip", firmware_version: null,
    flash: null, verified_by: null, verified_at: null, notes: "Discovery only; no board-specific artifact.",
    sources: [{ field: "board", url: "https://example.test/discovery", verified: "2026-09-04" }] };
}

test("atlas models only recorded parent and recipe edges, preserving full records and namespaces", () => {
  const chip = part("chip", "soc", "chip");
  const radioModule = part("module", "module", "chip", "module");
  const board = part("shared", "board", "chip", "module");
  const sibling = part("sibling", "board", "chip");
  const project = firmware("shared");
  const link = recipe("pair", "shared", "shared");
  const catalog = { parts: [chip, radioModule, board, sibling], firmware: [project], recipes: [link] };
  const model = buildAtlasModel(catalog);

  assert.equal(model.catalog, catalog);
  assert.equal(model.nodesByKey.get("part:shared")?.part, board);
  assert.equal(model.nodesByKey.get("firmware:shared")?.firmware, project);
  assert.equal(model.partsById.get("shared")?.psram_mb, 0);
  assert.equal(model.partsById.get("shared")?.bt_classic, false);
  assert.deepEqual(model.edges.map(({ from, to, kind }) => [from, to, kind]), [
    ["part:chip", "part:module", "lineage"],
    ["part:module", "part:shared", "lineage"],
    ["part:chip", "part:sibling", "lineage"],
    ["part:shared", "firmware:shared", "recipe"],
  ]);
  assert.equal(model.edges.at(-1)?.recipe, link);
  assert.deepEqual(model.gaps, []);
});

test("every trust tier, unknown status, caveat and citation survives without collapsing same-pair recipes", () => {
  const statuses = ["known-good", "reported", "declared", "unverified", "broken", "future-tier"];
  const recipes = statuses.map((status) => recipe(`pair-${status}`, "board", "project", status));
  const catalog = { parts: [part("board", "board", "chip"), part("chip", "soc", "chip")],
    firmware: [firmware("project")], recipes };
  const model = buildAtlasModel(catalog);
  assert.deepEqual(model.edges.filter((edge) => edge.kind === "recipe").map((edge) => edge.recipe), recipes);
  assert.deepEqual(model.recipesByBoard.get("board"), recipes);
  assert.deepEqual(model.recipesByFirmware.get("project"), recipes);
  for (const original of recipes) assert.equal(model.recipesById.get(original.id), original);
  assert.equal(new Set(model.edges.map((edge) => edge.key)).size, model.edges.length);
});

test("missing references remain explicit gaps; a module board never silently falls back to its inherited chip", () => {
  const catalog: AtlasCatalog = {
    parts: [part("chip", "soc", "chip"), part("board", "board", "chip", "missing-module")],
    firmware: [firmware("project")],
    recipes: [recipe("missing-board", "absent", "project"), recipe("missing-firmware", "board", "absent")],
  };
  const model = buildAtlasModel(catalog);
  assert.equal(model.nodes.length, 3);
  assert.deepEqual(model.edges, []);
  assert.equal(model.gaps.length, 3);
  assert.deepEqual(model.gaps.map((gap) => gap.referenceId), ["missing-module", "absent", "absent"]);
  assert.equal(model.recipesById.size, 2);
});

test("wrong-kind endpoints do not become lineage or board compatibility edges", () => {
  const model = buildAtlasModel({
    parts: [part("chip", "soc", "chip"), part("board", "board", null, "chip")],
    firmware: [firmware("project")], recipes: [recipe("wrong-kind", "chip", "project")],
  });
  assert.deepEqual(model.edges, []);
  assert.equal(model.gaps.length, 2);
  assert.ok(model.gaps.every((gap) => gap.kind === "invalid-reference"));
});

test("exactRecipe binds recipe identity to both endpoints, never to a guessed pair ID", () => {
  const one = recipe("opaque-id", "board", "project");
  const two = recipe("other-id", "board", "project", "broken");
  const catalog = { parts: [], firmware: [], recipes: [one, two] };
  assert.equal(exactRecipe(catalog, "opaque-id", "board", "project"), one);
  assert.equal(exactRecipe(catalog, "other-id", "board", "project"), two);
  assert.equal(exactRecipe(catalog, "opaque-id", "other", "project"), null);
  assert.equal(exactRecipe(catalog, "opaque-id", "board", "other"), null);
  assert.equal(exactRecipe(catalog, "board__project", "board", "project"), null);
});
