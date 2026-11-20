import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { analyticsBootScript, INTERNAL_KEY, OPT_OUT_KEY } from "./analytics-boot.ts";

const GA = "G-TEST123456";

/** Run the boot script the way the browser does: a fresh global with localStorage and location. */
function boot(search: string, stored: Record<string, string> = {}) {
  const store = new Map(Object.entries(stored));
  const ctx: Record<string, unknown> = {
    location: { search },
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
    },
  };
  ctx.window = ctx;
  vm.runInNewContext(analyticsBootScript(GA), ctx);
  // Objects made inside the VM have that realm's prototypes; JSON gives plain values to compare.
  const dataLayer = JSON.parse(JSON.stringify((ctx.dataLayer as unknown[]).map((entry) => Array.from(entry as ArrayLike<unknown>))));
  return { ctx, store, dataLayer };
}

test("?internal=1 marks this browser internal and every later hit carries internal=1", () => {
  const { store, dataLayer, ctx } = boot("?internal=1");
  assert.equal(store.get(INTERNAL_KEY), "1");
  assert.deepEqual(dataLayer, [["config", GA, { internal: "1" }]]);
  assert.equal(ctx.__ESP_ATLAS_GA_ID, GA);
});

test("the flag persists across visits without the query and ?internal=0 clears it", () => {
  assert.deepEqual(boot("", { [INTERNAL_KEY]: "1" }).dataLayer, [["config", GA, { internal: "1" }]]);
  const cleared = boot("?utm_source=x&internal=0", { [INTERNAL_KEY]: "1" });
  assert.equal(cleared.store.has(INTERNAL_KEY), false);
  assert.deepEqual(cleared.dataLayer, []);
});

test("visitors are untouched: no flag, no config command; lookalike params do nothing", () => {
  assert.deepEqual(boot("").dataLayer, []);
  assert.deepEqual(boot("?internal=yes").dataLayer, []);
  assert.deepEqual(boot("?notinternal=1").dataLayer, []);
});

test("the opt-out still disables collection, independently of the internal flag", () => {
  const { ctx } = boot("?internal=1", { [OPT_OUT_KEY]: "1" });
  assert.equal(ctx[`ga-disable-${GA}`], true);
});

test("storage that throws never breaks the page", () => {
  const ctx: Record<string, unknown> = {
    location: { search: "?internal=1" },
    localStorage: { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); }, removeItem() {} },
  };
  ctx.window = ctx;
  assert.doesNotThrow(() => vm.runInNewContext(analyticsBootScript(GA), ctx));
  assert.equal((ctx.dataLayer as unknown[]).length, 0);
});
