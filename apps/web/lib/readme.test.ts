import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchReadme, resolveReadmeHref } from "./readme.ts";

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
    assert.deepEqual(result, { markdown: "# hello", owner: "robo8080", repo: "AI_StackChan2_README", branch: "main", file: "README.md" });
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
    assert.deepEqual(result, { markdown: "body", owner: "o", repo: "r", branch: "master", file: "readme.md" });
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

test("rejects a README whose declared size exceeds the optional 256 KiB budget", async () => {
  const stub = stubFetch(() => new Response("large", { status: 200, headers: { "content-length": "262145" } }));
  try {
    assert.equal(await fetchReadme("https://github.com/o/r"), null);
    assert.equal(stub.calls.length, 1);
  } finally {
    stub.restore();
  }
});

test("enforces the README byte budget when the server omits content-length", async () => {
  const stub = stubFetch(() => new Response("x".repeat(262145), { status: 200 }));
  try {
    assert.equal(await fetchReadme("https://github.com/o/r"), null);
    assert.equal(stub.calls.length, 1);
  } finally {
    stub.restore();
  }
});

test("strips a trailing .git suffix from the repo name", async () => {
  const stub = stubFetch((url) =>
    url === "https://raw.githubusercontent.com/o/r/main/README.md" ? new Response("x", { status: 200 }) : new Response("", { status: 404 }),
  );
  try {
    const result = await fetchReadme("https://github.com/o/r.git");
    assert.deepEqual(result, { markdown: "x", owner: "o", repo: "r", branch: "main", file: "README.md" });
  } finally {
    stub.restore();
  }
});

test("README links resolve against the fetched repository branch and path", () => {
  const readme = { markdown: "", owner: "o", repo: "r", branch: "master", file: "docs/README.md" };
  assert.equal(resolveReadmeHref("../src/config.json#options", readme), "https://github.com/o/r/blob/master/src/config.json#options");
  assert.equal(resolveReadmeHref("/examples/", readme), "https://github.com/o/r/tree/master/examples");
  assert.equal(resolveReadmeHref("#install", readme), "https://github.com/o/r/blob/master/docs/README.md#install");
  assert.equal(resolveReadmeHref("https://example.com/a", readme), "https://example.com/a");
  assert.equal(resolveReadmeHref("./docs/guide.md", null, "https://github.com/o/r"), "https://github.com/o/r");
});

test("verified stale upstream links use a live target or become plain text", () => {
  const readme = (owner: string, repo: string) => ({ markdown: "", owner, repo, branch: "main", file: "README.md" });
  assert.equal(resolveReadmeHref("BUILDIgNG.md", readme("clackups", "draftling")), "https://github.com/clackups/draftling/blob/main/BUILDING.md");
  assert.equal(resolveReadmeHref("releases", readme("laserir", "MCLite")), "https://github.com/laserir/MCLite/releases");
  assert.equal(resolveReadmeHref("releases", readme("matoslav", "MicroGroove")), "https://github.com/matoslav/MicroGroove/releases");
  assert.equal(resolveReadmeHref("releases", readme("Artem76228", "PaperWeb")), "https://github.com/Artem76228/PaperWeb/releases");
  assert.equal(resolveReadmeHref("LICENSE", readme("Devsur11", "M5Gotchi")), null);
  assert.equal(resolveReadmeHref("LICENSE", readme("vanshksingh", "M5Cardputer-Chat-with-Gemini-API")), null);
  assert.equal(resolveReadmeHref("development", readme("1technophile", "OpenMQTTGateway")), null);
  assert.equal(resolveReadmeHref("src/ricoh", readme("sky18Dragon", "RICOH-GR-Live-View-Shooting")), null);
  assert.equal(resolveReadmeHref("LICENSE", readme("o", "r")), "https://github.com/o/r/blob/main/LICENSE");
});
