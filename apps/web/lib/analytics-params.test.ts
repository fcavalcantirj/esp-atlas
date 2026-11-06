import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanEventParams, trackedEventParams } from "./analytics-params.ts";

test("private prompt, search, and URL values cannot enter custom event payloads", () => {
  const secret = "private@example.com token=abc123";
  const clean = cleanEventParams({
    q: secret, needs: secret, extra: secret, url: `https://example.com/?q=${secret}`,
    prompt: secret, path: `/parts/${secret}`, part_id: "m5cardputer", result_count: 2,
  });
  assert.equal(clean.part_id, "m5cardputer");
  assert.equal(clean.result_count, 2);
  assert.equal(clean.q_length, secret.length);
  assert.ok(!JSON.stringify(clean).includes(secret));
  assert.ok(!("q" in clean) && !("url" in clean));
});

test("only eligible public model tokens reach the registered search dimension", () => {
  for (const [input, expected] of [[" fnk0104s ", "FNK0104S"], ["ES3C28P", "ES3C28P"], ["esp32-c6", "ESP32-C6"]]) {
    assert.equal(trackedEventParams("search_submit", { q: input }).q, expected);
    assert.equal(trackedEventParams("search_empty", { q: input }).q, expected);
    assert.ok(!("q" in trackedEventParams("search_results", { q: input })));
  }
  for (const input of ["private@example.com", "https://example.com/FNK0104S", "FNK0104S token=abc123", "my API key 123", "ES3C28P pinout", "AKIA1234567890ABCDEF", "(not set)", "", "ZZ9Q41X"]) {
    assert.ok(!("q" in trackedEventParams("search_submit", { q: input })), input);
    assert.ok(!("q" in trackedEventParams("search_empty", { q: input })), input);
  }
  assert.ok(!("q" in trackedEventParams("intent_submit", { q: "FNK0104S" })));
});
