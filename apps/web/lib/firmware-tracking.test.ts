import { test } from "node:test";
import assert from "node:assert/strict";
import {
  firmwareBrowseClickParams,
  firmwareRevealParams,
  firmwareSortParams,
  firmwareViewParams,
} from "./firmware-tracking.ts";

test("part_view params for a firmware record use part_type 'firmware' and the firmware's own id", () => {
  const params = firmwareViewParams("esphome", "esphome", "esp32");
  assert.equal(params.part_id, "esphome");
  assert.equal(params.part_type, "firmware");
  assert.equal(params.brand, "esphome");
  assert.equal(params.soc_ref, "esp32");
});

test("brand is null when the firmware has no recorded maintainer", () => {
  const params = firmwareViewParams("esphome", null, "esp32");
  assert.equal(params.brand, null);
});

test("soc_ref is null when the firmware has no recorded chip families", () => {
  const params = firmwareViewParams("esphome", "esphome", null);
  assert.equal(params.soc_ref, null);
});

test("result_click params for a browse-surface FirmwareCard fix origin to 'browse' and use the firmware's own id", () => {
  const params = firmwareBrowseClickParams("esphome");
  assert.equal(params.part_id, "esphome");
  assert.equal(params.part_type, "firmware");
  assert.equal(params.origin, "browse");
});

test("firmware_sort params carry the target mode and the mode it replaces", () => {
  const params = firmwareSortParams("name", "popularity");
  assert.equal(params.sort, "name");
  assert.equal(params.from, "popularity");
});

test("reveal_more params for the firmware browse list name the surface and report the pre-click count", () => {
  const params = firmwareRevealParams(20, 57);
  assert.equal(params.surface, "firmware");
  assert.equal(params.revealed, 20);
  assert.equal(params.total, 57);
});
