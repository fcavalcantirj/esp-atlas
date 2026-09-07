// POST /api/submit — turn "here is my firmware repo" into a GitHub issue labelled `submission`.
//
// The site never writes catalog data. The issue is opened by the EspAtlas Jr bot account
// (SUBMIT_GITHUB_TOKEN, a classic `public_repo` token) and Jr scores it on its next tick with
// the same deterministic rules as every other candidate, then comments the verdict and closes
// it. Gates here, cheapest first: strict URL parse, per-IP rate limit (best effort on a
// serverless instance), Cloudflare Turnstile verified server-side (the real bot gate), the repo
// must exist and be public, and an open submission for the same repo is returned instead of
// duplicated. Inert (503) until SUBMIT_GITHUB_TOKEN and TURNSTILE_SECRET_KEY are set.
import { cleanBoardsHint, clientIp, issueBody, issueTitle, parseRepoUrl, rateLimited, type Bucket } from "@/lib/submit";

const REPO_SLUG = process.env.SUBMIT_REPO_SLUG || "fcavalcantirj/esp-atlas";
const LABEL = "submission";
const bucket: Bucket = new Map();

type Json = Record<string, unknown>;

function json(body: Json, status = 200): Response {
  return Response.json(body, { status, headers: { "cache-control": "no-store" } });
}

async function verifyTurnstile(token: string, secret: string, ip: string): Promise<boolean> {
  const form = new URLSearchParams({ secret, response: token, remoteip: ip });
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST", body: form, signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) return false;
  const data = (await res.json()) as { success?: boolean };
  return data.success === true;
}

async function gh(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`https://api.github.com/${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "user-agent": "esp-atlas-submit/0.1 (+https://esp-atlas.com/submit)",
      "x-github-api-version": "2022-11-28",
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(15_000),
  });
}

export async function POST(request: Request) {
  const token = process.env.SUBMIT_GITHUB_TOKEN;
  const secret = process.env.TURNSTILE_SECRET_KEY;
  if (!token || !secret) return json({ error: "submissions not configured" }, 503);

  let payload: { repo?: unknown; boards?: unknown; turnstile?: unknown };
  try {
    payload = (await request.json()) as typeof payload;
  } catch {
    return json({ error: "expected a JSON body" }, 400);
  }
  const ref = parseRepoUrl(typeof payload.repo === "string" ? payload.repo : "");
  if (!ref) return json({ error: "that is not a GitHub repository URL (https://github.com/owner/repo)" }, 400);
  const boards = cleanBoardsHint(typeof payload.boards === "string" ? payload.boards : "");
  const ip = clientIp(request.headers.get("x-forwarded-for"));
  if (rateLimited(bucket, ip, Date.now())) return json({ error: "too many submissions from this address; try again in an hour" }, 429);

  const turnstile = typeof payload.turnstile === "string" ? payload.turnstile : "";
  if (!turnstile || !(await verifyTurnstile(turnstile, secret, ip))) {
    return json({ error: "the anti-bot check did not pass; reload and try again" }, 403);
  }

  // The repo must exist and be public (the bot's token sees only public repos anyway).
  const meta = await gh(`repos/${ref.owner}/${ref.repo}`, token);
  if (meta.status === 404) return json({ error: "no public GitHub repository at that URL" }, 404);
  if (!meta.ok) return json({ error: "GitHub did not answer; try again later" }, 502);
  const repo = (await meta.json()) as { full_name?: string; archived?: boolean; fork?: boolean };
  if (repo.archived) return json({ error: "archived repositories are not catalogued" }, 422);

  // One open submission per repo: hand back the existing issue instead of a duplicate.
  const q = encodeURIComponent(`repo:${REPO_SLUG} is:issue is:open label:${LABEL} "${ref.owner}/${ref.repo}" in:body`);
  const search = await gh(`search/issues?q=${q}&per_page=1`, token);
  if (search.ok) {
    const found = (await search.json()) as { items?: { html_url: string; number: number }[] };
    const hit = found.items?.[0];
    if (hit) return json({ issue_url: hit.html_url, issue: hit.number, existing: true });
  }

  const created = await gh(`repos/${REPO_SLUG}/issues`, token, {
    method: "POST",
    body: JSON.stringify({ title: issueTitle(ref), body: issueBody(ref, boards), labels: [LABEL] }),
    headers: { "content-type": "application/json" },
  });
  if (!created.ok) return json({ error: "could not open the submission; try again later" }, 502);
  const issue = (await created.json()) as { html_url: string; number: number };
  return json({ issue_url: issue.html_url, issue: issue.number, existing: false, repo: repo.full_name ?? ref.url, fork: repo.fork === true });
}
