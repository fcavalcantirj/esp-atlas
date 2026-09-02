import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchFirmwareList, fetchFirmware } from "./api-server.ts";

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

test("server fetches bypass the Next.js Data Cache with cache: 'no-store'", async () => {
  const stub = stubFetch(() => new Response(JSON.stringify({ results: [] }), { status: 200 }));
  try {
    await fetchFirmwareList();
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].cache, "no-store");
    // Regression guard: no `next.revalidate`, which is what let a deleted
    // firmware entry keep rendering from Next's persistent Data Cache.
    assert.equal((stub.calls[0] as Record<string, unknown>).next, undefined);
  } finally {
    stub.restore();
  }
});

test("server fetches still carry an AbortSignal.timeout signal", async () => {
  const stub = stubFetch(() => new Response(JSON.stringify({ id: "x" }), { status: 200 }));
  try {
    await fetchFirmware("x");
    assert.equal(stub.calls.length, 1);
    assert.ok(stub.calls[0].signal instanceof AbortSignal);
  } finally {
    stub.restore();
  }
});

test("a 404 from a stale/deleted firmware entry surfaces as not_found, not a cached hit", async () => {
  const stub = stubFetch(() => new Response(null, { status: 404 }));
  try {
    const result = await fetchFirmware("ruview");
    assert.deepEqual(result, { status: "not_found" });
  } finally {
    stub.restore();
  }
});
