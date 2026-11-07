// Synthetic UI fixtures, not catalog assertions. Enough rows to cross every reveal boundary.
export const firmware = Array.from({ length: 49 }, (_, i) => ({
  id: `fixture-${String(i).padStart(2, "0")}`, type: "firmware",
  name: i < 2 ? "Equal name" : `Project ${String(i).padStart(2, "0")}`,
  url: "https://example.com/fixture", category: "multi", maintainer: null, license: null,
  capabilities: [], socs: ["esp32"], sources: [], distribution: [], manifest_url: null,
  popularity: { stars: i === 48 ? null : Math.floor((48 - i) / 2), forks: i === 48 ? null : i, as_of: "2026-09-20", ...(i === 0 ? { github_as_of: "2026-11-06T17:00:00Z", downloads_as_of: "2026-10-01" } : {}) },
  boards: i % 7,
}));
// Only these synthetic repositories opt into the detail overlay tests. Their
// identities are fixtures; the test server blocks all upstream README fetches.
for (const [index, record] of firmware.slice(0, 2).entries()) {
  record.url = `https://github.com/atlas-fixture/project-${index}`;
  Object.assign(record.popularity, { github_repo_id: 100 + index, github_as_of: "2026-11-06T17:00:00Z" });
  record.sources = ["popularity.github_repo_id", "popularity.github_as_of"].map(field => ({ field, url: record.url, verified: "2026-11-06" }));
}
// The fixture API owns ordering, as the real API does. Browser tests compare the full output.
export function orderedFirmware(sort = "popularity") {
  const name = (a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
  const metric = (a, b, field) => (b.popularity[field] ?? -1) - (a.popularity[field] ?? -1);
  const stars = (a, b) => metric(a, b, "stars") || metric(a, b, "forks") || name(a, b);
  return [...firmware].sort(sort === "name" ? name : sort === "name-desc" ? (a, b) => -name(a, b)
    : sort === "forks" ? (a, b) => metric(a, b, "forks") || stars(a, b)
    : sort === "boards" ? (a, b) => b.boards - a.boards || stars(a, b) : stars);
}
export const board = { id: "fixture-board", name: "Fixture board", type: "board", vendor_or_brand: "fixture",
  brand_name: "Fixture", sources: [], score: 1, reasons: [], soc_ref: "esp32", _path: "fixture" };
export const guide = { firmware: "cardputer-iss-tracker", firmware_name: "Satellite/ISS Tracker",
  summary: "Recorded recipe evidence only.", requires: [], not_required: [], requirements: [],
  boards: [{ board_id: "fixture-board", board_name: "Fixture board", fit: "unconfirmed", status: "unverified",
    reasons: [], particularities: [], requires: [], not_required: [], sources: [] }],
  flash_next: [], citations: [], grounded: true };
export const intent = { kind: "firmware", firmware: "cardputer-iss-tracker", firmware_name: "Satellite/ISS Tracker",
  filters: {}, understood: [], unmapped: [], boards: [], board_reasons: [], cached: true };
export const build = { goal: "a fixture project", needs: [], firmware: null, boards: [], note: "No matching recipe is recorded." };
