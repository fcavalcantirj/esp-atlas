import { test } from "node:test";
import assert from "node:assert/strict";
import { firmwareViewParams } from "./firmware-tracking.ts";

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
