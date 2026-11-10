import { test } from "node:test";
import assert from "node:assert/strict";
import { CATALOG_TAG, fetchFirmware, fetchFirmwareList, serverApiHeaders } from "./api-server.ts";

function stubFetch(handler: (input: string, init: RequestInit) => Response) {
  const calls: RequestInit[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push(init ?? {});
    return handler(String(input), init ?? {});
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

test("server fetches stay in the Data Cache, tagged so a purge can reach them", async () => {
  const stub = stubFetch(() => new Response(JSON.stringify({ results: [] }), { status: 200 }));
  try {
    await fetchFirmwareList();
    assert.equal(stub.calls.length, 1);
    const init = stub.calls[0] as Record<string, unknown>;
    // Regression guard: `cache: "no-store"` (0c8ce8c) sent every render to a cold Python
    // function and was reverted (9a3a614). The cache stays; deletions are purged by tag.
    assert.equal(init.cache, undefined);
    assert.deepEqual(init.next, { revalidate: 240, tags: [CATALOG_TAG, "popularity"] });
    assert.equal(CATALOG_TAG, "catalog");
  } finally {
    stub.restore();
  }
});

test("fetchFirmwareList omits ?sort= for the default (popularity) mode", async () => {
  const stub = stubFetch(() => new Response(JSON.stringify({ results: [] }), { status: 200 }));
  try {
    await fetchFirmwareList("popularity");
    assert.equal(stub.calls.length, 1);
  } finally {
    stub.restore();
  }
});

test("fetchFirmwareList forwards a non-default sort as ?sort=", async () => {
  const urls: string[] = [];
  const stub = stubFetch((input) => {
    urls.push(input);
    return new Response(JSON.stringify({ results: [] }), { status: 200 });
  });
  try {
    await fetchFirmwareList("name-desc");
    assert.ok(urls[0].endsWith("/firmware?sort=name-desc"), urls[0]);
  } finally {
    stub.restore();
  }
});

test("entity fetches carry the same tag and an AbortSignal.timeout signal", async () => {
  const stub = stubFetch(() => new Response(JSON.stringify({ id: "x" }), { status: 200 }));
  try {
    await fetchFirmware("x");
    assert.equal(stub.calls.length, 1);
    const init = stub.calls[0] as Record<string, unknown>;
    assert.deepEqual(init.next, { revalidate: 240, tags: [CATALOG_TAG, "popularity"] });
    assert.ok(init.signal instanceof AbortSignal);
  } finally {
    stub.restore();
  }
});

test("preview self-fetch uses the deployment bypass only for its own API origin", () => {
  const keys = ["VERCEL_ENV", "VERCEL_URL", "VERCEL_AUTOMATION_BYPASS_SECRET"] as const;
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  try {
    process.env.VERCEL_ENV = "preview";
    process.env.VERCEL_URL = "preview.example.vercel.app";
    process.env.VERCEL_AUTOMATION_BYPASS_SECRET = "test-only-secret";
    assert.deepEqual(serverApiHeaders("https://preview.example.vercel.app/api"), { "x-vercel-protection-bypass": "test-only-secret" });
    assert.equal(serverApiHeaders("https://production.example.com/api"), undefined);
    assert.equal(serverApiHeaders("https://preview.example.vercel.app/other"), undefined);
    process.env.VERCEL_ENV = "production";
    assert.equal(serverApiHeaders("https://preview.example.vercel.app/api"), undefined);
  } finally {
    for (const key of keys) {
      const value = previous[key];
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
