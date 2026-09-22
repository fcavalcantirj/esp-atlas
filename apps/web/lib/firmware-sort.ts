// SPEC-firmware-ordering.md §2/§3: the /firmware sort control's own logic,
// kept pure and free of "@/" imports so it's node:test-able without a bundler
// (see lib/faq-jsonld.test.ts) -- page.tsx is just JSX glue over this.
// The API is the sort authority (Golden Rule 3); this module never orders
// anything, it only knows which modes exist and which URL/robots each maps to.

export const DEFAULT_SORT = "popularity";

export interface SortOption {
  value: string;
  label: string;
  /** Fragment for the /firmware lead sentence: "N ... projects, LEAD — open one...". */
  lead: string;
}

// Order matches SPEC-firmware-ordering.md §2's v1 table. `popularity`'s
// `lead` is the exact phrase the page used before this mode existed --
// changing it would break the "default view byte-identical to today" rule.
export const SORT_OPTIONS: SortOption[] = [
  { value: "popularity", label: "Most stars", lead: "ranked by GitHub popularity" },
  { value: "name", label: "Name (A→Z)", lead: "sorted A→Z by name" },
  { value: "name-desc", label: "Name (Z→A)", lead: "sorted Z→A by name" },
  { value: "forks", label: "Most forks", lead: "sorted by most forks" },
  { value: "boards", label: "Runs on most boards", lead: "sorted by boards supported" },
];

const VALID_SORTS = new Set(SORT_OPTIONS.map((o) => o.value));

/** Normalizes a raw `searchParams.sort` value (string | string[] | undefined,
 * exactly what Next hands generateMetadata/page) to a known mode. Unknown or
 * missing clamps to the default, mirroring the API's own clamp rule so the
 * UI and API can never disagree about what an unrecognized value means. */
export function resolveSort(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && VALID_SORTS.has(value) ? value : DEFAULT_SORT;
}

/** The href for a sort option link -- bare `/firmware` for the default so the
 * indexable canonical URL is exactly what the default option points at. */
export function sortHref(sort: string): string {
  return sort === DEFAULT_SORT ? "/firmware" : `/firmware?sort=${encodeURIComponent(sort)}`;
}

/** The /firmware page's lead sentence. Empty-list wording is unchanged from
 * before this mode existed; the populated wording keeps the exact original
 * phrase for `popularity` (byte-identical default view) and states the
 * active mode for every other sort. */
export function firmwareLeadCopy(sort: string, count: number): string {
  if (count === 0) return "The firmware list could not be loaded right now — try again in a moment.";
  const option = SORT_OPTIONS.find((o) => o.value === sort) ?? SORT_OPTIONS[0];
  return `${count} flashable firmware projects, ${option.lead} — open one to see the boards it's verified to run on.`;
}

export type FirmwareRobots = { index: boolean; follow: boolean } | undefined;

/** SPEC-firmware-ordering.md §3: bare /firmware (default sort) stays the
 * indexable canonical; every other order is noindex,follow so the alternate
 * orders never become indexable near-duplicates. A cold/unreachable API stays
 * noindex regardless of sort (SPEC-firmware-popularity.md's existing rule). */
export function firmwareRobots(sort: string, apiOk: boolean): FirmwareRobots {
  if (!apiOk || sort !== DEFAULT_SORT) return { index: false, follow: true };
  return undefined;
}
