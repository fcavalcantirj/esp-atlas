import { test } from "node:test";
import assert from "node:assert/strict";
import { matchBoard, type BoardRecord, type DetectedChip } from "./verify-board.ts";

// Cardputer: chip esp32-s3 / flash 8 / psram 0 (no PSRAM) — every field agrees.
const CARDPUTER_DETECTED: DetectedChip = {
  chipFamily: "esp32-s3",
  flashMb: 8,
  psram: { present: false, sizeMb: null },
  mac: "aa:bb:cc:dd:ee:ff",
};
const CARDPUTER_BOARD: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };

test("all fields match — Cardputer example", () => {
  const result = matchBoard(CARDPUTER_DETECTED, CARDPUTER_BOARD);
  assert.equal(result.overall, "match");
  assert.deepEqual(
    result.fields.map((f) => f.verdict),
    ["match", "match", "match"],
  );
  const chip = result.fields.find((f) => f.name === "Chip family")!;
  assert.equal(chip.detected, "esp32-s3");
  assert.equal(chip.cited, "esp32-s3");
  const flash = result.fields.find((f) => f.name === "Flash size")!;
  assert.equal(flash.detected, "8 MB");
  assert.equal(flash.cited, "8 MB");
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.detected, "no PSRAM");
  assert.equal(psram.cited, "no PSRAM");
  assert.equal(result.mac, "aa:bb:cc:dd:ee:ff");
});

test("chip family mismatch — e.g. StickC-Plus2 record picked but silicon is esp32-s3", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 4, psram: { present: false, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32", flashMb: 4, psramMb: 0 };
  const result = matchBoard(detected, board);
  const chip = result.fields.find((f) => f.name === "Chip family")!;
  assert.equal(chip.verdict, "mismatch");
  assert.equal(chip.detected, "esp32-s3");
  assert.equal(chip.cited, "esp32");
  assert.equal(result.overall, "mismatch");
});

test("flash size mismatch", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 4, psram: { present: false, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };
  const result = matchBoard(detected, board);
  const flash = result.fields.find((f) => f.name === "Flash size")!;
  assert.equal(flash.verdict, "mismatch");
  assert.equal(flash.detected, "4 MB");
  assert.equal(flash.cited, "8 MB");
  assert.equal(result.overall, "mismatch");
});

test("PSRAM mismatch — cited 0 (no PSRAM), silicon reads 2MB present", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 8, psram: { present: true, sizeMb: 2 }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };
  const result = matchBoard(detected, board);
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.verdict, "mismatch");
  assert.equal(psram.detected, "2 MB");
  assert.equal(psram.cited, "no PSRAM");
  assert.equal(result.overall, "mismatch");
});

test("PSRAM mismatch — cited 2MB, silicon reads no PSRAM", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 8, psram: { present: false, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 2 };
  const result = matchBoard(detected, board);
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.verdict, "mismatch");
  assert.equal(psram.detected, "no PSRAM");
  assert.equal(psram.cited, "2 MB");
});

test("PSRAM match on presence when the chip's own feature string gives no exact size", () => {
  const detected: DetectedChip = { chipFamily: "esp32", flashMb: 4, psram: { present: true, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32", flashMb: 4, psramMb: 4 };
  const result = matchBoard(detected, board);
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.verdict, "match");
  assert.equal(psram.detected, "present (size unknown)");
  assert.equal(psram.cited, "4 MB");
});

test("unknown — chip family not read (detect failed before it could report)", () => {
  const detected: DetectedChip = { chipFamily: null, flashMb: 8, psram: { present: false, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };
  const result = matchBoard(detected, board);
  const chip = result.fields.find((f) => f.name === "Chip family")!;
  assert.equal(chip.verdict, "unknown");
  assert.equal(chip.detected, "not read");
  assert.equal(result.overall, "unknown");
});

test("unknown — cited record has no psram_mb value to check against", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 8, psram: { present: true, sizeMb: 8 }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: null };
  const result = matchBoard(detected, board);
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.verdict, "unknown");
  assert.equal(psram.cited, "not cited");
});

test("unknown — PSRAM feature read failed entirely (loader.chip.getChipFeatures threw)", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: 8, psram: null, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };
  const result = matchBoard(detected, board);
  const psram = result.fields.find((f) => f.name === "PSRAM")!;
  assert.equal(psram.verdict, "unknown");
  assert.equal(psram.detected, "not read");
});

test("overall is unknown, not match, when one field is unknown and none mismatch", () => {
  const detected: DetectedChip = { chipFamily: "esp32-s3", flashMb: null, psram: { present: false, sizeMb: null }, mac: null };
  const board: BoardRecord = { soc: "esp32-s3", flashMb: 8, psramMb: 0 };
  const result = matchBoard(detected, board);
  assert.equal(result.overall, "unknown");
});
