import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { elapsedBucket, flashOutcome, isInstallDialogFor } from "./flash-outcome.ts";

// esp-web-tools 10.4.0 (pinned): <ewt-install-dialog> keeps the last FlashState it received in its
// `_installState` (install-dialog.js:929) until it closes, then fires a bubbling, composed `closed`
// event (fire-event.js; install-dialog.js:983). State names: initializing, preparing, erasing,
// writing, finished, error (install-dialog.js:608-672).
const dialog = (installState: unknown, manifestPath = "/api/flash/r1/manifest.json") =>
  ({ localName: "ewt-install-dialog", manifestPath, _installState: installState });

test("the outcome is read from the dialog's last flash state", () => {
  assert.deepEqual(flashOutcome(dialog({ state: "finished", chipFamily: "ESP32-S3", details: { percentage: 100 } })),
    { result: "success", stage: "finished", chip: "ESP32-S3" });
  assert.deepEqual(flashOutcome(dialog({ state: "error", chipFamily: "ESP32", message: "Failed to initialize" })),
    { result: "failed", stage: "error", chip: "ESP32" });
  assert.deepEqual(flashOutcome(dialog({ state: "writing", chipFamily: "ESP32-C3", details: { percentage: 41 } })),
    { result: "aborted", stage: "writing", chip: "ESP32-C3" });
  assert.deepEqual(flashOutcome(dialog({ state: "erasing" })), { result: "aborted", stage: "erasing", chip: undefined });
});

test("closing before any install, or a shape this version never had, says so instead of guessing", () => {
  assert.deepEqual(flashOutcome(dialog(undefined)), { result: "not_started", stage: "none", chip: undefined });
  assert.deepEqual(flashOutcome(dialog({ state: "provisioning" })), { result: "unknown", stage: "provisioning", chip: undefined });
  assert.deepEqual(flashOutcome(dialog("finished")), { result: "unknown", stage: "unreadable", chip: undefined });
});

test("only this recipe's dialog counts: another manifest or another element is ignored", () => {
  assert.equal(isInstallDialogFor(dialog(undefined), "/api/flash/r1/manifest.json"), true);
  assert.equal(isInstallDialogFor(dialog(undefined, "/api/flash/r2/manifest.json"), "/api/flash/r1/manifest.json"), false);
  assert.equal(isInstallDialogFor({ localName: "ewt-other", manifestPath: "/api/flash/r1/manifest.json" }, "/api/flash/r1/manifest.json"), false);
  assert.equal(isInstallDialogFor(null, "/api/flash/r1/manifest.json"), false);
});

test("elapsed time goes out as a coarse bucket, never a raw duration", () => {
  assert.equal(elapsedBucket(4_000), "lt_15s");
  assert.equal(elapsedBucket(40_000), "15s_1m");
  assert.equal(elapsedBucket(150_000), "1m_5m");
  assert.equal(elapsedBucket(900_000), "gt_5m");
});

test("the reading is tied to the pinned esp-web-tools version", () => {
  // a bump must re-verify install-dialog.js (`_installState`, the `closed` event) before this test changes
  const src = readFileSync(new URL("./esp-web-tools.ts", import.meta.url), "utf8");
  assert.match(src, /export const ESP_WEB_TOOLS_VERSION = "10\.4\.0";/);
});
