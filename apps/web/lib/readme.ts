// Best-effort README fetch for the firmware detail page's inline preview.
// Spike, frontend-only: no backend/API involvement, nothing persisted.

const BRANCHES = ["main", "master"];
const FILES = ["README.md", "readme.md", "README.MD", "README"];
const REVALIDATE_SECONDS = 86400;
const TOTAL_BUDGET_MS = 3000;
const MAX_README_BYTES = 256 * 1024;

export interface RepoReadme {
  markdown: string;
  owner: string;
  repo: string;
  branch: string;
  file: string;
}

/** A README link is relative to its repository file, never to /firmware/<id>. */
export function resolveReadmeHref(href: string, readme: RepoReadme | null, repoFallbackUrl = ""): string {
  if (/^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)) return href;
  // Translated README text can outlive an upstream fetch failure. Keep its
  // relative links useful without guessing a branch or emitting Atlas 404s.
  if (!readme) return repoFallbackUrl || "#firmware-readme";
  const base = `https://github.com/${encodeURIComponent(readme.owner)}/${encodeURIComponent(readme.repo)}`;
  const [pathAndQuery, fragment = ""] = href.split("#", 2);
  const [path, query = ""] = pathAndQuery.split("?", 2);
  const input = !path ? readme.file : path.startsWith("/") ? path.slice(1) : `${readme.file.includes("/") ? readme.file.slice(0, readme.file.lastIndexOf("/") + 1) : ""}${path}`;
  const segments: string[] = [];
  for (const segment of input.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") segments.pop();
    else segments.push(segment);
  }
  const target = segments.join("/") || readme.file;
  const isDirectory = path.endsWith("/") || (!/\.[^/]+$/.test(target) && !/^(?:README|LICENSE|NOTICE|Makefile|Dockerfile|AGENTS)$/i.test(target.split("/").at(-1) ?? ""));
  const encoded = target.split("/").map(encodeURIComponent).join("/");
  return `${base}/${isDirectory ? "tree" : "blob"}/${encodeURIComponent(readme.branch)}/${encoded}${query ? `?${query}` : ""}${fragment ? `#${fragment}` : ""}`;
}

function parseGithubRepo(repoUrl: string): { owner: string; repo: string } | null {
  let url: URL;
  try {
    url = new URL(repoUrl);
  } catch {
    return null;
  }
  if (url.hostname !== "github.com") return null;
  const [owner, repo] = url.pathname.split("/").filter(Boolean);
  if (!owner || !repo) return null;
  return { owner, repo: repo.replace(/\.git$/, "") };
}

async function boundedReadmeText(response: Response): Promise<string | null> {
  const declaredBytes = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredBytes) && declaredBytes > MAX_README_BYTES) {
    await response.body?.cancel().catch(() => {});
    return null;
  }
  if (!response.body) return "";

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const chunks: string[] = [];
  let bytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_README_BYTES) {
        await reader.cancel().catch(() => {});
        return null;
      }
      chunks.push(decoder.decode(value, { stream: true }));
    }
    chunks.push(decoder.decode());
    return chunks.join("");
  } finally {
    reader.releaseLock();
  }
}

export async function fetchReadme(repoUrl: string): Promise<RepoReadme | null> {
  const parsed = parseGithubRepo(repoUrl);
  if (!parsed) return null;
  const { owner, repo } = parsed;
  const deadline = Date.now() + TOTAL_BUDGET_MS;

  for (const branch of BRANCHES) {
    for (const file of FILES) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) return null;
      try {
        const res = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${file}`, {
          next: { revalidate: REVALIDATE_SECONDS },
          signal: AbortSignal.timeout(remaining),
        });
        if (res.status === 200) {
          const markdown = await boundedReadmeText(res);
          if (markdown === null) return null;
          return { markdown, owner, repo, branch, file };
        }
      } catch {
        // Network error or expired budget. Continue only while time remains.
      }
    }
  }
  return null;
}
