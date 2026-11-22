// Snapshot isolation (Jr redesign plan, step 1, 2026-11-22). In production the server used to read the
// catalog through the production ALIAS (VERCEL_PROJECT_PRODUCTION_URL). Vercel's Data Cache survives
// deployments and is keyed by URL, so a new deployment could render pages from the previous deployment's
// API. Each deployment now reads its OWN API (https://$VERCEL_URL/api, with the project's automation-bypass
// header, which Vercel injects into every deployment), so cache keys differ per deployment. The header must
// never leave that origin, and no catalog read may happen during `next build` (the deployment's own API
// does not exist yet).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fetchFacets, serverApiBase, serverApiHeaders } from "./api-server.ts";
import { loadAtlasCatalog } from "./atlas-load.ts";

const KEYS = ["VERCEL_ENV", "VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_AUTOMATION_BYPASS_SECRET",
  "API_INTERNAL_URL", "NEXT_PUBLIC_API_URL", "NEXT_PHASE"] as const;

function withEnv(env: Partial<Record<(typeof KEYS)[number], string>>, fn: () => void | Promise<void>) {
  const saved = Object.fromEntries(KEYS.map((k) => [k, process.env[k]]));
  for (const k of KEYS) delete process.env[k];
  Object.assign(process.env, env);
  const restore = () => {
    for (const k of KEYS) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  };
  try {
    const r = fn();
    if (r instanceof Promise) return r.finally(restore);
    restore();
  } catch (e) {
    restore();
    throw e;
  }
}

const PROD = { VERCEL_ENV: "production", VERCEL_URL: "esp-atlas-abc123.vercel.app",
  VERCEL_PROJECT_PRODUCTION_URL: "esp-atlas.com", VERCEL_AUTOMATION_BYPASS_SECRET: "test-only-secret" };

function stubFetch(handler: () => Response = () => new Response(JSON.stringify({ results: [] }), { status: 200 })) {
  const calls: { url: string; init: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    return handler();
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = original; } };
}

test("production reads its own deployment's API, not the alias, when the bypass secret is present", () =>
  withEnv(PROD, () => {
    assert.equal(serverApiBase(), "https://esp-atlas-abc123.vercel.app/api");
    assert.deepEqual(serverApiHeaders("https://esp-atlas-abc123.vercel.app/api"), { "x-vercel-protection-bypass": "test-only-secret" });
  }));

test("production without the bypass secret keeps the alias (a protected own URL would 401)", () =>
  withEnv({ ...PROD, VERCEL_AUTOMATION_BYPASS_SECRET: undefined as unknown as string }, () => {
    delete process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
    assert.equal(serverApiBase(), "https://esp-atlas.com/api");
    assert.equal(serverApiHeaders("https://esp-atlas.com/api"), undefined);
  }));

test("the bypass header is never attached to any base but the deployment's own API", () =>
  withEnv(PROD, () => {
    for (const base of ["https://esp-atlas.com/api", "https://evil.example/api", "https://esp-atlas-abc123.vercel.app/other",
      "http://esp-atlas-abc123.vercel.app/api", "https://esp-atlas-abc123.vercel.app.evil.example/api"]) {
      assert.equal(serverApiHeaders(base), undefined, base);
    }
  }));

test("server catalog fetches refuse redirects, so the bypass header cannot follow one to another host", async () =>
  withEnv(PROD, async () => {
    const stub = stubFetch();
    try {
      await fetchFacets();
      await loadAtlasCatalog(serverApiBase());
      assert.ok(stub.calls.length >= 4);
      for (const c of stub.calls) assert.equal(c.init.redirect, "error", c.url);
    } finally {
      stub.restore();
    }
  }));

test("during `next build` no catalog read touches the network (the deployment's own API does not exist yet)", async () =>
  withEnv({ ...PROD, NEXT_PHASE: "phase-production-build" }, async () => {
    const stub = stubFetch();
    try {
      const facets = await fetchFacets();
      const atlas = await loadAtlasCatalog(serverApiBase());
      assert.equal(stub.calls.length, 0);
      assert.equal(facets.status, "error");
      assert.equal(atlas.status, "error");
    } finally {
      stub.restore();
    }
  }));

test("pages and route handlers under app/ read the catalog only through the guarded helpers", () => {
  // The only direct fetch() calls allowed under app/ are the external-service submit route and the atlas
  // verification scripts (tooling, not rendered). Anything else must go through lib/api-server.ts or
  // lib/atlas-load.ts, where the build guard, the redirect policy and the own-deployment base live.
  const allowed = new Set(["app/api/submit/route.ts", "app/atlas/verification/verify-workflows.mjs",
    "app/atlas/verification/verify-trust.mjs"]);
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(tsx?|mjs)$/.test(name) && !name.includes(".test.")) {
        const text = readFileSync(p, "utf8");
        if (/\bfetch\(/.test(text) && !text.includes('"use client"') && !allowed.has(p)) offenders.push(p);
      }
    }
  };
  walk("app");
  assert.deepEqual(offenders, []);
});

test("no recipe-derived route pre-renders catalog ids at build", () => {
  for (const p of ["app/firmware/[id]/page.tsx", "app/parts/[id]/page.tsx", "app/brands/[brand]/page.tsx"]) {
    const text = readFileSync(p, "utf8");
    const m = text.match(/export function generateStaticParams\(\)\s*\{([^}]*)\}/);
    assert.ok(m, `${p} defines generateStaticParams`);
    assert.match(m[1], /return \[\];/, `${p} must pre-render nothing`);
  }
});

test("every route that reads the catalog declares how it refreshes, so the build guard cannot bake it static", () => {
  // Review BLOCK on #1984 (2026-11-22): /debug's only refresh setting came from its build-time fetch. With no
  // catalog read during `next build`, Next would have baked it fully static with an empty board list. A file
  // under app/ (outside app/api/, whose handlers are dynamic) that imports a catalog helper must export
  // `revalidate`/`dynamic`, call `connection()`, or sit under a dynamic [segment] (rendered on demand).
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { if (p !== join("app", "api")) walk(p); continue; }
      if (!/\.(tsx?)$/.test(name) || name.includes(".test.")) continue;
      const text = readFileSync(p, "utf8");
      if (!/from "@\/lib\/(api-server|atlas-server)"/.test(text)) continue;
      const declares = /export const (revalidate|dynamic)\b/.test(text) || /\bawait connection\(\)/.test(text)
        || /export (async )?function generateStaticParams/.test(text);
      if (!declares && !/\[[^\]]+\]/.test(p)) offenders.push(p);
    }
  };
  walk("app");
  assert.deepEqual(offenders, []);
});
