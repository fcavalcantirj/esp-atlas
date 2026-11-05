import test from "node:test";
import assert from "node:assert/strict";
import { atlasPartDetail } from "./atlas-detail.ts";
const detail = { id: "board-a", body: "Cited notes.", chain: { soc: { id: "chip-a", name: "Chip A" }, module: null }, sources: [{ field: "*", url: "https://vendor.test/a", verified: "2026-11-05" }] };
test("valid detail retains its complete cited notes and lineage", () => {
  assert.equal(atlasPartDetail(detail, "board-a"), detail);
  assert.equal(atlasPartDetail(detail, "other-board"), null);
});
test("malformed success payloads cannot enter the inspector success state", () => {
  for (const patch of [{ sources: [null] }, { sources: [{}] }, { body: {} }, { chain: true }, { chain: { soc: {}, module: null } }, { chain: { soc: null } }]) {
    assert.equal(atlasPartDetail({ ...detail, ...patch }, "board-a"), null);
  }
});
