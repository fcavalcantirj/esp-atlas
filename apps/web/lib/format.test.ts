import { test } from "node:test";
import assert from "node:assert/strict";
import { readmeLanguageName } from "./format.ts";

test("maps known README source language codes to an English name", () => {
  assert.equal(readmeLanguageName("ja"), "Japanese");
  assert.equal(readmeLanguageName("zh"), "Chinese");
  assert.equal(readmeLanguageName("ko"), "Korean");
});

test("falls back to the raw code for an unmapped language", () => {
  assert.equal(readmeLanguageName("fr"), "fr");
});
