import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanEventParams } from "./analytics-params.ts";

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
