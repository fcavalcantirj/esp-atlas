import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchReadme } from "./readme.ts";

function stubFetch(handler: (url: string) => Response) {
  const calls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request) => {
    const url = String(input);
    calls.push(url);
    return handler(url);
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

test("non-github URLs resolve to null without a network call", async () => {
  const stub = stubFetch(() => new Response("", { status: 200 }));
  try {
    const result = await fetchReadme("https://gitlab.com/owner/repo");
    assert.equal(result, null);
    assert.equal(stub.calls.length, 0);
  } finally {
    stub.restore();
  }
});

test("returns the first 200 response as markdown + owner/repo, tagged for a day-long revalidate", async () => {
  const stub = stubFetch((url) =>
    url === "https://raw.githubusercontent.com/robo8080/AI_StackChan2_README/main/README.md"
      ? new Response("# hello", { status: 200 })
      : new Response("", { status: 404 }),
  );
  try {
    const result = await fetchReadme("https://github.com/robo8080/AI_StackChan2_README");
    assert.deepEqual(result, { markdown: "# hello", owner: "robo8080", repo: "AI_StackChan2_README" });
    assert.equal(stub.calls[0], "https://raw.githubusercontent.com/robo8080/AI_StackChan2_README/main/README.md");
  } finally {
    stub.restore();
  }
});

test("falls through branches and filenames until one hits, then stops", async () => {
  const stub = stubFetch((url) =>
    url === "https://raw.githubusercontent.com/o/r/master/readme.md"
      ? new Response("body", { status: 200 })
      : new Response("", { status: 404 }),
  );
  try {
    const result = await fetchReadme("https://github.com/o/r");
    assert.deepEqual(result, { markdown: "body", owner: "o", repo: "r" });
    assert.equal(stub.calls.length, 6);
  } finally {
    stub.restore();
  }
});

test("returns null when every branch/filename combination misses", async () => {
  const stub = stubFetch(() => new Response("", { status: 404 }));
  try {
    const result = await fetchReadme("https://github.com/o/r");
    assert.equal(result, null);
    assert.equal(stub.calls.length, 8);
  } finally {
    stub.restore();
  }
});

test("never throws -- a network error is swallowed and treated as a miss", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new Error("network down");
  }) as typeof fetch;
  try {
    const result = await fetchReadme("https://github.com/o/r");
    assert.equal(result, null);
  } finally {
    globalThis.fetch = original;
  }
});

test("strips a trailing .git suffix from the repo name", async () => {
  const stub = stubFetch((url) =>
    url === "https://raw.githubusercontent.com/o/r/main/README.md" ? new Response("x", { status: 200 }) : new Response("", { status: 404 }),
  );
  try {
    const result = await fetchReadme("https://github.com/o/r.git");
    assert.deepEqual(result, { markdown: "x", owner: "o", repo: "r" });
  } finally {
    stub.restore();
  }
});
