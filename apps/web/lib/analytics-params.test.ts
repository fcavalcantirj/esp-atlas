import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cleanEventParams, trackedEventParams } from "./analytics-params.ts";

const demandContract = JSON.parse(readFileSync(new URL("./analytics-demand-contract.json", import.meta.url), "utf8")) as {
  eligible: { input: string; emitted: string; submits: number; empty: number }[];
  excluded: string[];
};

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
  for (const { input, emitted } of demandContract.eligible) {
    assert.equal(trackedEventParams("search_submit", { q: input }).q, emitted);
    assert.equal(trackedEventParams("search_empty", { q: input }).q, emitted);
    assert.ok(!("q" in trackedEventParams("search_results", { q: input })));
  }
  assert.equal(trackedEventParams("search_submit", { q: "esp32-c6" }).q, "ESP32-C6");
  for (const input of [...demandContract.excluded, "my API key 123", "ES3C28P pinout", "ZZ9Q41X"]) {
    assert.ok(!("q" in trackedEventParams("search_submit", { q: input })), input);
    assert.ok(!("q" in trackedEventParams("search_empty", { q: input })), input);
  }
  assert.ok(!("q" in trackedEventParams("intent_submit", { q: "FNK0104S" })));
});
