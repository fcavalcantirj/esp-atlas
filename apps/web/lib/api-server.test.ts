import { test } from "node:test";
import assert from "node:assert/strict";
import { CATALOG_TAG, fetchFirmware, fetchFirmwareList } from "./api-server.ts";

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
    assert.deepEqual(init.next, { revalidate: 3600, tags: [CATALOG_TAG] });
    assert.equal(CATALOG_TAG, "catalog");
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
    assert.deepEqual(init.next, { revalidate: 3600, tags: [CATALOG_TAG] });
    assert.ok(init.signal instanceof AbortSignal);
  } finally {
    stub.restore();
  }
});
