// Builds GitHub URLs for the "contribute" affordances (header/footer links,
// per-part edit/view-source links). No business logic — just URL shaping.
const DEFAULT_REPO_URL = "https://github.com/fcavalcantirj/esp-atlas";

const REPO_URL = (process.env.NEXT_PUBLIC_REPO_URL || DEFAULT_REPO_URL).replace(/\/+$/, "");

export function repoUrl(): string {
  return REPO_URL;
}

export function contributingUrl(): string {
  return `${REPO_URL}/blob/main/CONTRIBUTING.md`;
}

export function agentsUrl(): string {
  return `${REPO_URL}/blob/main/AGENTS.md`;
}

export function licenseUrl(): string {
  return `${REPO_URL}/blob/main/LICENSE`;
}

export function llmsTxtUrl(): string {
  return `${REPO_URL}/blob/main/llms.txt`;
}

export function dataFolderUrl(): string {
  return `${REPO_URL}/tree/main/data`;
}

export function discussionsUrl(): string {
  return `${REPO_URL}/discussions`;
}

export function issuesUrl(): string {
  return `${REPO_URL}/issues`;
}

export function newIssueUrl(opts: { title: string; body?: string }): string {
  const params = new URLSearchParams({ title: opts.title });
  if (opts.body) params.set("body", opts.body);
  return `${REPO_URL}/issues/new?${params.toString()}`;
}

export function editSourceUrl(path: string): string {
  return `${REPO_URL}/edit/main/${path}`;
}

export function viewSourceUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path}`;
}
