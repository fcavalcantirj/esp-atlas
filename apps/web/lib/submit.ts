// Pure helpers for the /submit box and POST /api/submit (app/api/submit/route.ts).
//
// A submission never writes catalog data. The route turns "here is my repo" into a GitHub issue
// labelled `submission`, opened by the EspAtlas Jr bot; Jr scores it on its next tick with the
// same deterministic rules as every other candidate (25 stars or 25 forks, not a fork of a
// catalogued firmware, a catalogued board named) and comments the verdict. Trash can only ever
// become a closed issue with a reason. These helpers are pure so they run under `node --test`.

export type RepoRef = { owner: string; repo: string; url: string };

const REPO_URL = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)\/([A-Za-z0-9._-]{1,100}?)(?:\.git)?\/?(?:[#?].*)?$/;
const RESERVED_OWNERS = new Set(["orgs", "settings", "marketplace", "features", "topics", "explore", "login", "join", "about", "pricing", "sponsors"]);

/** Strict parse of a GitHub repository URL. Anything else → null. */
export function parseRepoUrl(input: string | null | undefined): RepoRef | null {
  const raw = (input ?? "").trim();
  if (!raw || raw.length > 300) return null;
  const m = REPO_URL.exec(raw);
  if (!m) return null;
  const owner = m[1];
  const repo = m[2];
  if (RESERVED_OWNERS.has(owner.toLowerCase())) return null;
  if (repo === "." || repo === ".." || /^\.+$/.test(repo)) return null;
  return { owner, repo, url: `https://github.com/${owner}/${repo}` };
}

/** The "Boards" hint, trimmed, single line, bounded. Empty → null. */
export function cleanBoardsHint(input: string | null | undefined): string | null {
  const s = (input ?? "").replace(/[\r\n\t]+/g, " ").replace(/\s{2,}/g, " ").trim();
  if (!s) return null;
  return s.slice(0, 200);
}

export function issueTitle(ref: RepoRef): string {
  return `Submission: ${ref.owner}/${ref.repo}`;
}

/** Body in the shape the issue form produces, so jr/stage_admit.parse_submission reads both alike. */
export function issueBody(ref: RepoRef, boards: string | null): string {
  const lines = ["### Repository URL", "", ref.url, "", "### Boards", "", boards ?? "_No response_", "",
    "_Submitted from esp-atlas.com/submit. EspAtlas Jr scores it on its next tick and comments the verdict here._"];
  return lines.join("\n");
}

/** Sliding-window rate limit, per key, in-memory (best effort on serverless; Turnstile is the real gate). */
export type Bucket = Map<string, number[]>;

export function rateLimited(bucket: Bucket, key: string, now: number, limit = 5, windowMs = 60 * 60 * 1000): boolean {
  const cutoff = now - windowMs;
  const hits = (bucket.get(key) ?? []).filter((t) => t > cutoff);
  if (hits.length >= limit) {
    bucket.set(key, hits);
    return true;
  }
  hits.push(now);
  bucket.set(key, hits);
  return false;
}

/** First address of x-forwarded-for, else the fallback. */
export function clientIp(forwardedFor: string | null, fallback = "unknown"): string {
  const first = (forwardedFor ?? "").split(",")[0]?.trim();
  return first || fallback;
}
