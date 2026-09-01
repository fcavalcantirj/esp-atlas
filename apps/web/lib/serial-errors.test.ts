import { test } from "node:test";
import assert from "node:assert/strict";
import { friendlySerialError, isPortAlreadyOpen, PORT_ALREADY_OPEN_MESSAGE } from "./serial-errors.ts";

// The real DOMException Chrome throws when the port is held open elsewhere has
// name "InvalidStateError" and a message containing "already open".
function invalidState(): Error {
  const e = new Error("Failed to execute 'open' on 'SerialPort': The port is already open.");
  e.name = "InvalidStateError";
  return e;
}

test("InvalidStateError maps to the friendly 'already open' message", () => {
  const e = invalidState();
  assert.equal(isPortAlreadyOpen(e), true);
  assert.equal(friendlySerialError(e, "fallback"), PORT_ALREADY_OPEN_MESSAGE);
});

test("a message containing 'already open' maps to the friendly message even without the name", () => {
  const e = new Error("The port is Already Open");
  assert.equal(isPortAlreadyOpen(e), true);
  assert.equal(friendlySerialError(e, "fallback"), PORT_ALREADY_OPEN_MESSAGE);
});

test("an unrelated error falls back to the caller's message", () => {
  const e = new Error("No chip detected — check the wiring");
  assert.equal(isPortAlreadyOpen(e), false);
  assert.equal(friendlySerialError(e, "fallback"), "fallback");
});

test("a non-Error value falls back", () => {
  assert.equal(isPortAlreadyOpen("boom"), false);
  assert.equal(friendlySerialError("boom", "fallback"), "fallback");
});
