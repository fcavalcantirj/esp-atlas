// SPEC-firmware-search.md §3: the /firmware search + filter state, kept pure and free of "@/" imports so it is
// node:test-able without a bundler (like lib/firmware-sort.ts). The API filters and orders (Golden Rule 3);
// this module only knows which parameters exist, how a URL spells them, and what the page says about them.
import { DEFAULT_SORT, SORT_OPTIONS, resolveSort } from "./firmware-sort.ts";

export const RELEVANCE_SORT = "relevance";
export const MAX_QUERY = 120;

export interface FirmwareQuery {
  q: string;
  board: string;
  soc: string;
  category: string;
  capability: string;
  tested: boolean;
  /** "" = no explicit order: the API's default (popularity, or relevance when `q` is set). */
  sort: string;
}

export interface FacetOption {
  id: string;
  count: number;
  name?: string | null;
}

export interface FirmwareFacets {
  boards: FacetOption[];
  socs: FacetOption[];
  categories: FacetOption[];
  capabilities: FacetOption[];
  catalog_total: number;
}

type Raw = string | string[] | undefined;
type RawParams = Record<string, Raw>;

function one(raw: Raw): string {
  return ((Array.isArray(raw) ? raw[0] : raw) ?? "").trim();
}

/** A filter value as the URL may carry it: a short id-like token, or nothing. */
function token(raw: Raw): string {
  const value = one(raw).toLowerCase();
  return /^[a-z0-9][a-z0-9._-]{0,79}$/.test(value) ? value : "";
}

/** Normalizes Next's `searchParams` to the page's query. Unknown or malformed values become "nothing set",
 * so a hand-edited URL can never produce a state the form cannot show. */
export function parseFirmwareQuery(params: RawParams): FirmwareQuery {
  // Cut by code point, never through a surrogate pair: half an emoji makes encodeURIComponent throw.
  const q = Array.from(one(params.q).replace(/\s+/g, " ")).filter((c) => !/^[\uD800-\uDFFF]$/.test(c)).slice(0, MAX_QUERY).join("").trim();
  const rawSort = one(params.sort);
  const sort = rawSort === RELEVANCE_SORT ? (q ? RELEVANCE_SORT : "") : rawSort && resolveSort(rawSort) === rawSort ? rawSort : "";
  return {
    q,
    board: token(params.board),
    soc: token(params.soc),
    category: token(params.category),
    capability: token(params.capability),
    tested: ["1", "true", "on"].includes(one(params.tested).toLowerCase()),
    sort: sort === DEFAULT_SORT && !q ? "" : sort,
  };
}

/** True when a search word or any filter is set (the order alone is not a filter). */
export function isFiltered(query: FirmwareQuery): boolean {
  return Boolean(query.q || query.board || query.soc || query.category || query.capability || query.tested);
}

/** How many filters (not counting the search words) are set. */
export function filterCount(query: FirmwareQuery): number {
  return [query.board, query.soc, query.category, query.capability].filter(Boolean).length + (query.tested ? 1 : 0);
}

/** The order the list is really in: the explicit one, else relevance with a query, else popularity. */
export function effectiveSort(query: FirmwareQuery): string {
  return query.sort || (query.q ? RELEVANCE_SORT : DEFAULT_SORT);
}

function pairs(query: FirmwareQuery): [string, string][] {
  const out: [string, string][] = [];
  if (query.q) out.push(["q", query.q]);
  if (query.board) out.push(["board", query.board]);
  if (query.soc) out.push(["soc", query.soc]);
  if (query.category) out.push(["category", query.category]);
  if (query.capability) out.push(["capability", query.capability]);
  if (query.tested) out.push(["tested", "1"]);
  if (query.sort) out.push(["sort", query.sort]);
  return out;
}

function encode(list: [string, string][]): string {
  return list.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
}

/** The query string the API gets ("" for the bare list, so the default request is byte-identical to before). */
export function apiQueryString(query: FirmwareQuery): string {
  const list = pairs(query);
  return list.length ? `?${encode(list)}` : "";
}

/** The page URL for a state: bare `/firmware` when nothing is set. `change` overrides fields (e.g. a sort link). */
export function firmwareHref(query: FirmwareQuery, change: Partial<FirmwareQuery> = {}): string {
  const next = { ...query, ...change };
  if (next.sort === DEFAULT_SORT && !next.q) next.sort = "";
  if (next.sort === RELEVANCE_SORT && next.q) next.sort = "";
  const list = pairs(next);
  return list.length ? `/firmware?${encode(list)}` : "/firmware";
}

/** The orders the control offers: "Best match" first, only while there are search words. */
export function sortChoices(query: FirmwareQuery): { value: string; label: string }[] {
  const base = SORT_OPTIONS.map(({ value, label }) => ({ value, label }));
  return query.q ? [{ value: RELEVANCE_SORT, label: "Best match" }, ...base] : base;
}

const LABELS: Record<string, string> = {
  multi: "Multi-tool", pentest: "Security testing", mesh: "Mesh networking", home: "Home automation",
  badusb: "BadUSB", display: "Display", wifi: "Wi-Fi", ble: "Bluetooth LE", lora: "LoRa", gps: "GPS",
  mqtt: "MQTT", ir: "Infrared", ota: "OTA updates", nfc: "NFC", "rfid-nfc": "RFID / NFC",
  "sub-ghz": "Sub-GHz", subghz: "Sub-GHz", "on-device-web-ui": "On-device web UI",
};

/** A readable label for a category or capability id; an unknown id is shown as it is, hyphens as spaces. */
export function optionLabel(id: string): string {
  return LABELS[id] ?? id.replace(/-/g, " ");
}

/** Chip family ids read as the part numbers people know: "esp32-s3" -> "ESP32-S3". */
export function socLabel(id: string): string {
  return id.toUpperCase();
}

/** "12 of 170 firmware projects" / "170 firmware projects". */
export function countLine(shown: number, catalogTotal: number | null | undefined, filtered: boolean): string {
  const noun = (n: number) => (n === 1 ? "firmware project" : "firmware projects");
  if (!filtered || !catalogTotal) return `${shown} ${noun(shown)}`;
  return `${shown} of ${catalogTotal} ${noun(catalogTotal)}`;
}

/** The lead sentence of a searched or filtered list. */
export function filteredLead(shown: number, catalogTotal: number | null | undefined): string {
  const count = `Showing ${countLine(shown, catalogTotal, true)}`;
  return shown === 0 ? `${count}.` : `${count} — open one to see the boards it has recipes for, by trust tier.`;
}

/** What the empty state says, naming what was asked for. */
export function emptyCopy(query: FirmwareQuery): string {
  const asked = query.q ? `“${query.q}”` : "these filters";
  const more = query.q && filterCount(query) > 0 ? " with these filters" : "";
  return `No firmware matches ${asked}${more}. Try fewer words or clear a filter.`;
}

export type Robots = { index: boolean; follow: boolean } | undefined;

/** SPEC-firmware-search.md §3: only the bare default list is indexable; any search, filter or other order is
 * noindex,follow (canonical stays /firmware), and so is a list the API could not serve. */
export function firmwareListRobots(query: FirmwareQuery, apiOk: boolean): Robots {
  if (!apiOk || isFiltered(query) || query.sort !== "") return { index: false, follow: true };
  return undefined;
}

/** `firmware_search` event params: never the words themselves, only whether there were any. */
export function firmwareSearchParams(query: FirmwareQuery, results: number): Record<string, string | number | boolean> {
  return { has_query: Boolean(query.q), filters: filterCount(query), sort: effectiveSort(query), result_count: results };
}
