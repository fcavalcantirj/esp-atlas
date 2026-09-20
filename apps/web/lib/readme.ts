// Best-effort README fetch for the firmware detail page's inline preview.
// Spike, frontend-only: no backend/API involvement, nothing persisted.

const BRANCHES = ["main", "master"];
const FILES = ["README.md", "readme.md", "README.MD", "README"];
const REVALIDATE_SECONDS = 86400;

export interface RepoReadme {
  markdown: string;
  owner: string;
  repo: string;
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

export async function fetchReadme(repoUrl: string): Promise<RepoReadme | null> {
  const parsed = parseGithubRepo(repoUrl);
  if (!parsed) return null;
  const { owner, repo } = parsed;

  for (const branch of BRANCHES) {
    for (const file of FILES) {
      try {
        const res = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${branch}/${file}`, {
          next: { revalidate: REVALIDATE_SECONDS },
        });
        if (res.status === 200) {
          const markdown = await res.text();
          return { markdown, owner, repo };
        }
      } catch {
        // Network error, timeout, etc. -- try the next branch/file combination.
      }
    }
  }
  return null;
}
