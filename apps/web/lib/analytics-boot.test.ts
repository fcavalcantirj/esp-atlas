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
  const all = JSON.parse(JSON.stringify((ctx.dataLayer as unknown[]).map((entry) => Array.from(entry as ArrayLike<unknown>)))) as unknown[][];
  // Consent commands are checked by their own tests below; the internal-flag tests look at the rest.
  const dataLayer = all.filter((e) => e[0] !== "consent");
  const consent = all.filter((e) => e[0] === "consent");
  return { ctx, store, dataLayer, consent, all };
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
  const rest = (ctx.dataLayer as ArrayLike<unknown>[]).filter((e) => Array.from(e)[0] !== "consent");
  assert.equal(rest.length, 0);
});


// --- Consent Mode v2 (2026-11-18, owner: banner for EEA/UK/CH only) ------------------------------------------

test("consent defaults come first: granted analytics worldwide, denied in the consent regions, ads denied everywhere", () => {
  const { all, consent } = boot("");
  assert.deepEqual(all[0][0], "consent");
  assert.deepEqual(consent[0], ["consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: "granted" }]);
  const regional = consent[1] as [string, string, Record<string, unknown>];
  assert.equal(regional[1], "default");
  assert.equal(regional[2].analytics_storage, "denied");
  assert.equal(regional[2].ad_storage, "denied");
  assert.equal((regional[2].region as string[]).length, 32);
  assert.ok((regional[2].region as string[]).includes("DE") && (regional[2].region as string[]).includes("GB"));
  assert.equal(regional[2].wait_for_update, 500);
  assert.equal(consent.length, 2);                                  // no stored choice: no update
});

test("a stored choice is replayed as a consent update before gtag loads", () => {
  assert.deepEqual(boot("", { "esp-atlas:consent": "granted" }).consent[2], ["consent", "update", { analytics_storage: "granted" }]);
  assert.deepEqual(boot("", { "esp-atlas:consent": "denied" }).consent[2], ["consent", "update", { analytics_storage: "denied" }]);
  assert.equal(boot("", { "esp-atlas:consent": "maybe" }).consent.length, 2);
});
