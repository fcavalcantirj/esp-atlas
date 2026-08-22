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

export function dataFolderUrl(): string {
  return `${REPO_URL}/tree/main/data`;
}

export function editSourceUrl(path: string): string {
  return `${REPO_URL}/edit/main/${path}`;
}

export function viewSourceUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path}`;
}
