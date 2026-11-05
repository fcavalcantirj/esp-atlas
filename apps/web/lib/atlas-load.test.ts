import { test } from "node:test";
import assert from "node:assert/strict";
import { loadAtlasCatalog } from "./atlas-load.ts";
import { fetchAtlasCatalog } from "./atlas-server.ts";

const part = {
  id: "board", type: "board", name: "Board", soc_ref: null, module_ref: null,
  vendor_or_brand: "test", brand_name: "Test", brand_url: null, wifi_standard: null, wifi_bands: null,
  ble_version: null, bt_classic: false, ieee802154: null, ieee802154_protocols: null,
  form_factor: null, price_tier: null, usb_native: null, flash_mb: null, psram_mb: 0,
  _path: "data/boards/test/board/board.md", sources: [],
};
const firmware = { id: "project", type: "firmware", name: "Project", url: "https://example.test/project",
  category: "multi", maintainer: null, license: null, distribution: [], manifest_url: null,
  capabilities: [], socs: [], sources: [], boards: 1, requires: [{ capability: "wifi", why: "Source rationale" }] };
const recipe = { id: "opaque-pair", type: "recipe", board: "board", firmware: "project", status: "unverified",
  chip_family: "chip", firmware_version: null, flash: null, verified_by: null, verified_at: null,
  notes: "Discovery only. No board-specific artifact; generic install is a four-file bundle, not a merged image.",
  sources: [{ field: "board", url: "https://example.test/discovery", verified: "2026-09-04" }] };

function envelopes(): Record<string, unknown> {
  return { "/parts": { results: [part] }, "/firmware": { results: [firmware], total: 1 }, "/recipes": { results: [recipe] } };
}

function respond(bodies = envelopes(), calls: string[] = []): typeof fetch {
  return (async (input) => {
    const path = new URL(String(input)).pathname;
    calls.push(path);
    return new Response(JSON.stringify(bodies[path]), { status: 200 });
  }) as typeof fetch;
}

test("loader starts all three complete collection requests before awaiting, preserving every wire field", async () => {
  const started: string[] = [];
  const releases: (() => void)[] = [];
  const bodies = envelopes();
  const fetcher = (async (input) => {
    const url = new URL(String(input));
    assert.equal(url.search, "");
    started.push(url.pathname);
    await new Promise<void>((resolve) => releases.push(resolve));
    return new Response(JSON.stringify(bodies[url.pathname]));
  }) as typeof fetch;
  const pending = loadAtlasCatalog("https://api.example.test", fetcher);
  assert.deepEqual(started, ["/parts", "/firmware", "/recipes"]);
  releases.forEach((release) => release());
  const result = await pending;
  assert.equal(result.status, "ok");
  if (result.status !== "ok") return;
  assert.deepEqual(result.catalog, { parts: [part], firmware: [firmware], recipes: [recipe] });
});

test("successful empty catalog differs from one or all unavailable endpoints", async () => {
  const empty = { "/parts": { results: [] }, "/firmware": { results: [], total: 0 }, "/recipes": { results: [] } };
  assert.deepEqual(await loadAtlasCatalog("https://api.example.test", respond(empty)),
    { status: "ok", catalog: { parts: [], firmware: [], recipes: [] } });
  for (const failed of [["/recipes"], ["/parts", "/firmware", "/recipes"]]) {
    const fetcher = (async (input) => {
      const path = new URL(String(input)).pathname;
      return failed.includes(path) ? new Response(null, { status: 503 }) : respond(empty)(input);
    }) as typeof fetch;
    const result = await loadAtlasCatalog("https://api.example.test", fetcher);
    assert.equal(result.status, "error");
    if (result.status === "error") for (const path of failed) assert.ok(result.message.includes(path));
    assert.equal("catalog" in result, false);
  }
});

test("malformed envelopes, records, evidence, duplicates and incomplete totals never become a full catalog", async () => {
  const cases: [string, unknown][] = [
    ["/parts", {}], ["/parts", { results: null }], ["/parts", { results: [null] }],
    ["/parts", { results: [{ ...part, sources: [{ url: "https://example.test" }] }] }],
    ["/parts", { results: [part, part] }],
    ["/firmware", { results: [firmware] }], ["/firmware", { results: [firmware], total: 2 }],
    ["/firmware", { results: [firmware], total: -1 }],
    ["/recipes", { results: [{ ...recipe, notes: 7 }] }],
    ["/recipes", { results: [{ ...recipe, flash: { method: 7 } }] }],
    ["/recipes", { results: [recipe], total: 2 }],
  ];
  for (const [endpoint, body] of cases) {
    const result = await loadAtlasCatalog("https://api.example.test", respond({ ...envelopes(), [endpoint]: body }));
    assert.equal(result.status, "error", JSON.stringify(body));
    if (result.status === "error") assert.ok(result.message.includes(endpoint));
  }
});

test("a parts response at the API cap is not claimed complete without an authoritative matching total", async () => {
  const parts = Array.from({ length: 10_000 }, (_, i) => ({ ...part, id: `part-${i}` }));
  const result = await loadAtlasCatalog("https://api.example.test", respond({ ...envelopes(), "/parts": { results: parts } }));
  assert.equal(result.status, "error");
  if (result.status === "error") assert.match(result.message, /cap|complete|truncat/i);
});

test("firmware recipe counts detect a silently incomplete recipes collection without discarding missing-reference records", async () => {
  const missing = await loadAtlasCatalog("https://api.example.test", respond({ ...envelopes(), "/recipes": { results: [] } }));
  assert.equal(missing.status, "error");
  if (missing.status === "error") assert.match(missing.message, /recipe.*count|count.*recipe/i);
  const orphan = { ...recipe, id: "orphan", firmware: "missing-project" };
  const withOrphan = await loadAtlasCatalog("https://api.example.test", respond({
    ...envelopes(), "/recipes": { results: [recipe, orphan] },
  }));
  assert.equal(withOrphan.status, "ok");
  if (withOrphan.status === "ok") assert.equal(withOrphan.catalog.recipes.length, 2);
});

test("only transport failures retry with 3s then 9s signals; HTTP and invalid JSON do not retry", async (t) => {
  const timeout = AbortSignal.timeout.bind(AbortSignal);
  const budgets: number[] = [];
  t.mock.method(AbortSignal, "timeout", (ms: number) => { budgets.push(ms); return timeout(ms); });
  const calls = new Map<string, number>();
  const fetcher = (async (input, init) => {
    const path = new URL(String(input)).pathname;
    const attempt = (calls.get(path) ?? 0) + 1;
    calls.set(path, attempt);
    assert.ok(init?.signal instanceof AbortSignal);
    if (path === "/parts" && attempt === 1) throw new TypeError("network unavailable");
    return respond()(input, init);
  }) as typeof fetch;
  assert.equal((await loadAtlasCatalog("https://api.example.test", fetcher)).status, "ok");
  assert.equal(calls.get("/parts"), 2);
  assert.deepEqual(budgets.toSorted(), [3000, 3000, 3000, 9000]);

  for (const response of [() => new Response(null, { status: 404 }), () => new Response("invalid json")]) {
    const failedCalls: string[] = [];
    const bad = (async (input) => { failedCalls.push(String(input)); return response(); }) as typeof fetch;
    assert.equal((await loadAtlasCatalog("https://api.example.test", bad)).status, "error");
    assert.equal(failedCalls.length, 3);
  }
});

test("server entry point keeps catalog-tagged hourly cache and never disables caching", async (t) => {
  const requests: { url: string; init: RequestInit & { next?: unknown } }[] = [];
  t.mock.method(globalThis, "fetch", (async (input, init) => {
    requests.push({ url: String(input), init: init ?? {} });
    return respond()(input, init);
  }) as typeof fetch);
  assert.equal((await fetchAtlasCatalog()).status, "ok");
  assert.equal(requests.length, 3);
  for (const { url, init } of requests) {
    assert.match(url, /^https?:\/\//);
    assert.deepEqual(init.next, { revalidate: 3600, tags: ["catalog"] });
    assert.equal(init.cache, undefined);
  }
});
