import assert from "node:assert/strict";
import { test } from "node:test";
import { cleanBoardsHint, clientIp, issueBody, issueTitle, parseRepoUrl, rateLimited } from "./submit.ts";

test("parseRepoUrl accepts the shapes people paste and normalizes them", () => {
  for (const s of ["https://github.com/clackups/draftling", "http://github.com/clackups/draftling/", "github.com/clackups/draftling.git",
    "https://www.github.com/clackups/draftling?tab=readme", "  https://github.com/clackups/draftling#readme "]) {
    assert.deepEqual(parseRepoUrl(s), { owner: "clackups", repo: "draftling", url: "https://github.com/clackups/draftling" });
  }
});

test("parseRepoUrl rejects everything that is not one public repo", () => {
  for (const s of ["", null, undefined, "https://gitlab.com/o/r", "https://github.com/onlyowner", "https://github.com/o/r/tree/main",
    "https://github.com/orgs/foo", "https://github.com/o/..", "javascript:alert(1)", "https://github.com/o/r; rm -rf", "x".repeat(301)]) {
    assert.equal(parseRepoUrl(s), null, `should reject ${String(s).slice(0, 40)}`);
  }
});

test("issue title and body match the issue form's shape", () => {
  const ref = parseRepoUrl("https://github.com/clackups/draftling")!;
  assert.equal(issueTitle(ref), "Submission: clackups/draftling");
  const body = issueBody(ref, "M5Stack PaperS3, LilyGO T5 E-Paper S3 Pro");
  assert.match(body, /^### Repository URL\n\nhttps:\/\/github\.com\/clackups\/draftling\n\n### Boards\n\nM5Stack PaperS3, LilyGO T5 E-Paper S3 Pro\n/);
  assert.match(issueBody(ref, null), /### Boards\n\n_No response_/);
});

test("cleanBoardsHint flattens and bounds the hint", () => {
  assert.equal(cleanBoardsHint("  M5Stack\n PaperS3,   T-Deck \t"), "M5Stack PaperS3, T-Deck");
  assert.equal(cleanBoardsHint(""), null);
  assert.equal(cleanBoardsHint("a".repeat(500))!.length, 200);
});

test("rateLimited allows the limit within the window and refuses the next", () => {
  const b = new Map<string, number[]>();
  const t0 = 1_000_000;
  for (let i = 0; i < 5; i++) assert.equal(rateLimited(b, "ip", t0 + i * 1000, 5, 60_000), false);
  assert.equal(rateLimited(b, "ip", t0 + 6000, 5, 60_000), true);
  assert.equal(rateLimited(b, "other", t0 + 6000, 5, 60_000), false);
  assert.equal(rateLimited(b, "ip", t0 + 61_001, 5, 60_000), false);   // the window slid
});

test("clientIp takes the first forwarded address", () => {
  assert.equal(clientIp("1.2.3.4, 5.6.7.8"), "1.2.3.4");
  assert.equal(clientIp(null), "unknown");
});
