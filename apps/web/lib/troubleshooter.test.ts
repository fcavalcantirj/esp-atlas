import { test } from "node:test";
import assert from "node:assert/strict";
import { downloadModeView, firstFlashNotes, GENERIC_DOWNLOAD_STEPS, resolveDownloadMode, type BootBoard } from "./troubleshooter.ts";

// The real GET /api/boards/boot record for esp32-c5-devkitc-1 (see its
// board.md frontmatter) — the board the /debug troubleshooter prefills.
const C5: BootBoard = {
  id: "esp32-c5-devkitc-1",
  name: "ESP32-C5-DevKitC-1",
  download_mode: {
    mode: "manual",
    steps: "Hold down Boot, then press Reset, then release Boot to enter Firmware Download mode",
    note: "Two USB-C ports: the USB-to-UART port for serial flashing, or the native ESP32-C5 USB port (USB-Serial-JTAG).",
  },
  usb_serial: "native-usb-serial-jtag",
  first_flash_notes: [
    "J5 current-measurement header: its jumper must be fitted (factory default = jumper on). Without it, per the user guide, \"power supply between the module and peripherals on the board is cut off\".",
  ],
};

test("default (no board selected) shows the generic ESP32 sequence", () => {
  const view = resolveDownloadMode(null);
  assert.equal(view.steps, GENERIC_DOWNLOAD_STEPS);
  assert.equal(view.steps, "Hold BOOT, tap RESET, then release BOOT");
  assert.equal(view.isGeneric, true);
  assert.equal(view.note, null);
});

test("selecting a board renders that board's cited steps + note", () => {
  const view = resolveDownloadMode(C5);
  assert.equal(view.steps, C5.download_mode.steps);
  assert.equal(view.note, C5.download_mode.note);
  assert.equal(view.isGeneric, false);
});

test("a 'manual' board with no cited steps falls back to the generic sequence", () => {
  const board: BootBoard = { id: "x", name: "X", download_mode: { mode: "manual" } };
  const view = resolveDownloadMode(board);
  assert.equal(view.steps, GENERIC_DOWNLOAD_STEPS);
  assert.equal(view.note, null);
  assert.equal(view.isGeneric, false);
});

test("an 'auto' board says no buttons are needed, not the generic sequence", () => {
  const board: BootBoard = { id: "auto-1", name: "Auto Board", download_mode: { mode: "auto" } };
  const view = resolveDownloadMode(board);
  assert.notEqual(view.steps, GENERIC_DOWNLOAD_STEPS);
  assert.match(view.steps, /automatically/i);
  assert.equal(view.isGeneric, false);
});

// downloadModeView is what the flash panel (FlashAction) uses directly, from a
// board's frontmatter `download_mode` — no BootBoard wrapper.
test("downloadModeView(undefined) is the generic fallback (board with no cited steps)", () => {
  const view = downloadModeView(undefined);
  assert.equal(view.steps, GENERIC_DOWNLOAD_STEPS);
  assert.equal(view.isGeneric, true);
  assert.equal(view.note, null);
});

test("downloadModeView renders a manual board's cited steps + note", () => {
  const view = downloadModeView(C5.download_mode);
  assert.equal(view.steps, C5.download_mode.steps);
  assert.equal(view.note, C5.download_mode.note);
  assert.equal(view.isGeneric, false);
});

test("resolveDownloadMode delegates to downloadModeView on the board's download_mode", () => {
  assert.deepEqual(resolveDownloadMode(C5), downloadModeView(C5.download_mode));
});

// first_flash_notes — the cited power-jumper gotcha the C5 shipped with (2026-09-01).
test("a board's cited first-flash notes are returned verbatim", () => {
  const notes = firstFlashNotes(C5);
  assert.equal(notes.length, 1);
  assert.match(notes[0], /J5 current-measurement header/);
});

test("no board, no field, an empty list and blank entries all yield []", () => {
  assert.deepEqual(firstFlashNotes(null), []);
  assert.deepEqual(firstFlashNotes({ id: "x", name: "X", download_mode: { mode: "auto" } }), []);
  assert.deepEqual(firstFlashNotes({ id: "x", name: "X", download_mode: { mode: "auto" }, first_flash_notes: [] }), []);
  assert.deepEqual(firstFlashNotes({ id: "x", name: "X", download_mode: { mode: "auto" }, first_flash_notes: ["  ", ""] }), []);
  assert.deepEqual(firstFlashNotes({ id: "x", name: "X", download_mode: { mode: "auto" }, first_flash_notes: null }), []);
});

test("notes are trimmed, never re-worded", () => {
  const b: BootBoard = { id: "x", name: "X", download_mode: { mode: "auto" }, first_flash_notes: ["  fit the J5 jumper  "] };
  assert.deepEqual(firstFlashNotes(b), ["fit the J5 jumper"]);
});
