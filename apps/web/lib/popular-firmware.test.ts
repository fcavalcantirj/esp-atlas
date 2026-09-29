import { test } from "node:test";
import assert from "node:assert/strict";
import { POPULAR_FIRMWARE_LIMIT, selectPopularFirmware } from "./popular-firmware.ts";
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

test("orders by cited star count, descending", () => {
  const low = makeFirmware({ id: "low", popularity: { stars: 10 } });
  const high = makeFirmware({ id: "high", popularity: { stars: 500 } });
  const mid = makeFirmware({ id: "mid", popularity: { stars: 100 } });
  const result = selectPopularFirmware([low, high, mid]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["high", "mid", "low"],
  );
});

test("tiebreaks by boards count when stars are equal", () => {
  const fewBoards = makeFirmware({ id: "few", popularity: { stars: 200 }, boards: 2 });
  const manyBoards = makeFirmware({ id: "many", popularity: { stars: 200 }, boards: 20 });
  const result = selectPopularFirmware([fewBoards, manyBoards]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["many", "few"],
  );
});

test("tiebreaks by boards count when stars are absent on both", () => {
  const fewBoards = makeFirmware({ id: "few", boards: 3 });
  const manyBoards = makeFirmware({ id: "many", boards: 15 });
  const result = selectPopularFirmware([fewBoards, manyBoards]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["many", "few"],
  );
});

test("a firmware with a boards signal but no stars still ranks below any starred firmware", () => {
  const starred = makeFirmware({ id: "starred", popularity: { stars: 1 } });
  const boardsOnly = makeFirmware({ id: "boards-only", boards: 500 });
  const result = selectPopularFirmware([boardsOnly, starred]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["starred", "boards-only"],
  );
});

test("excludes a firmware with neither a cited star count nor a boards signal (cite-or-omit)", () => {
  const noSignal = makeFirmware({ id: "no-signal" });
  const starred = makeFirmware({ id: "starred", popularity: { stars: 5 } });
  const result = selectPopularFirmware([noSignal, starred]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["starred"],
  );
});

test("a firmware with zero stars and zero boards has no signal and is excluded", () => {
  const zeroSignal = makeFirmware({ id: "zero", popularity: { stars: 0 }, boards: 0 });
  const starred = makeFirmware({ id: "starred", popularity: { stars: 5 } });
  const result = selectPopularFirmware([zeroSignal, starred]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["starred"],
  );
});

test("never fabricates a rank: an all-no-signal list returns empty", () => {
  const a = makeFirmware({ id: "a" });
  const b = makeFirmware({ id: "b" });
  assert.deepEqual(selectPopularFirmware([a, b]), []);
});

test("caps the result at the given limit", () => {
  const firmware = Array.from({ length: 20 }, (_, i) =>
    makeFirmware({ id: `fw-${i}`, popularity: { stars: 20 - i } }),
  );
  const result = selectPopularFirmware(firmware, 5);
  assert.equal(result.length, 5);
  assert.deepEqual(
    result.map((f) => f.id),
    ["fw-0", "fw-1", "fw-2", "fw-3", "fw-4"],
  );
});

test("defaults the cap to POPULAR_FIRMWARE_LIMIT when no limit is given", () => {
  const firmware = Array.from({ length: POPULAR_FIRMWARE_LIMIT + 5 }, (_, i) =>
    makeFirmware({ id: `fw-${i}`, popularity: { stars: 100 - i } }),
  );
  const result = selectPopularFirmware(firmware);
  assert.equal(result.length, POPULAR_FIRMWARE_LIMIT);
});

test("stable ordering: equal stars and boards fall back to name, A→Z", () => {
  const zeta = makeFirmware({ id: "zeta", name: "Zeta", popularity: { stars: 50 }, boards: 4 });
  const alpha = makeFirmware({ id: "alpha", name: "Alpha", popularity: { stars: 50 }, boards: 4 });
  const result = selectPopularFirmware([zeta, alpha]);
  assert.deepEqual(
    result.map((f) => f.id),
    ["alpha", "zeta"],
  );
});

test("does not mutate the input array", () => {
  const firmware = [makeFirmware({ id: "b", popularity: { stars: 1 } }), makeFirmware({ id: "a", popularity: { stars: 2 } })];
  const copy = [...firmware];
  selectPopularFirmware(firmware);
  assert.deepEqual(firmware, copy);
});
