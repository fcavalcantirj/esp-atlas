// apps/web/scripts/ignore-build.sh is Vercel's Ignored Build Step (apps/web/vercel.json `ignoreCommand`):
// exit 0 skips the deployment, exit 1 builds it. 2026-11-21: 40 production deploys in 24 h, most of them
// Jr's hourly bookkeeping merges, and each new deployment starts with an empty page cache (Vercel's ISR
// documentation), so Googlebot kept meeting 2-4 s pages and stopped crawling the new ones.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const SCRIPT = resolve(import.meta.dirname, "..", "scripts", "ignore-build.sh");

function git(cwd: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd, encoding: "utf8" }).trim();
}

function put(root: string, rel: string, text: string) {
  const p = join(root, rel);
  mkdirSync(join(p, ".."), { recursive: true });
  writeFileSync(p, text);
}

function repo(): { root: string; base: string } {
  const root = mkdtempSync(join(tmpdir(), "ignore-build-"));
  git(root, "init", "-q", "-b", "main");
  git(root, "config", "user.email", "t@t");
  git(root, "config", "user.name", "t");
  for (const rel of ["apps/web/app/page.tsx", "data/firmware/x/firmware.md", "schema/board.schema.json",
                     "apps/core/src/esp_atlas_core/x.py", "apps/api/src/esp_atlas_api/x.py",
                     "jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl", "jr/tick.py", "SPEC.md", "llms.txt"]) {
    put(root, rel, "v1\n");
  }
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", "base");
  return { root, base: git(root, "rev-parse", "HEAD") };
}

function decide(root: string, prev: string | undefined): number {
  const env = { ...process.env, VERCEL_GIT_PREVIOUS_SHA: prev ?? "" };
  // Vercel runs the command in the project's Root Directory, apps/web
  return spawnSync("bash", [SCRIPT], { cwd: join(root, "apps", "web"), env, encoding: "utf8" }).status ?? -1;
}

function change(rel: string): number {
  const { root, base } = repo();
  put(root, rel, "v2\n");
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", `change ${rel}`);
  return decide(root, base);
}

test("a merge that only touches Jr's bookkeeping, Jr's code or the docs skips the deployment", () => {
  for (const rel of ["jr/proposed_ledger.json", "docs/telemetry/data-trend.jsonl", "jr/tick.py", "SPEC.md"]) {
    assert.equal(change(rel), 0, rel);
  }
});

test("a change to anything the site is built from deploys", () => {
  for (const rel of ["apps/web/app/page.tsx", "data/firmware/x/firmware.md", "schema/board.schema.json",
                     "apps/core/src/esp_atlas_core/x.py", "apps/api/src/esp_atlas_api/x.py", "llms.txt"]) {
    assert.equal(change(rel), 1, rel);
  }
});

test("it compares with the last SUCCESSFUL deployment, so a skipped or failed content change is not lost", () => {
  const { root, base } = repo();
  put(root, "data/firmware/x/firmware.md", "v2\n");           // a content merge whose deployment failed
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", "content");
  put(root, "jr/proposed_ledger.json", "v2\n");               // then a bookkeeping merge
  git(root, "add", "-A");
  git(root, "commit", "-q", "-m", "ledger");
  assert.equal(decide(root, base), 1);                        // still behind the last good deployment: build
});

test("every doubt builds: no previous deployment, or one this clone cannot read", () => {
  const { root } = repo();
  assert.equal(decide(root, undefined), 1);
  assert.equal(decide(root, "0123456789abcdef0123456789abcdef01234567"), 1);
});
