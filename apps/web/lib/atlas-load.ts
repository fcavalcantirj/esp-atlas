import type { Firmware, PartRecord, Recipe, SourceEntry } from "./api.ts";
import { CATALOG_TAG, serverApiHeaders } from "./api-server.ts";
import type { AtlasCatalog } from "./atlas-model.ts";

export type AtlasCatalogResult =
  | { status: "ok"; catalog: AtlasCatalog }
  | { status: "error"; message: string };

type ObjectValue = Record<string, unknown>;
export type CollectionResult<T> = { status: "ok"; records: T[] } | { status: "error"; message: string };
export type Guard<T> = (value: unknown) => value is T;

// apps/api/src/esp_atlas_api/main.py currently caps /parts at this value and
// supplies no total. Reaching it without a total cannot prove completeness.
const PARTS_CAP = 10_000;
const TIMEOUT_MS = 3000;
const COLD_START_TIMEOUT_MS = 9000;

function object(value: unknown): value is ObjectValue {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function string(value: unknown): value is string { return typeof value === "string"; }
function nonempty(value: unknown): value is string { return string(value) && value.trim().length > 0; }
function number(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value); }
function boolean(value: unknown): value is boolean { return typeof value === "boolean"; }
function nullable(value: unknown, guard: (value: unknown) => boolean): boolean { return value === null || guard(value); }
function strings(value: unknown): value is string[] { return Array.isArray(value) && value.every(string); }
function sources(value: unknown): value is SourceEntry[] {
  return Array.isArray(value) && value.every((entry) => object(entry) && nonempty(entry.field) && nonempty(entry.url) && nonempty(entry.verified));
}
function stringsAt(value: ObjectValue, keys: string[]): boolean { return keys.every((key) => string(value[key])); }
function nullableAt(value: ObjectValue, keys: string[], guard: (value: unknown) => boolean): boolean {
  return keys.every((key) => nullable(value[key], guard));
}

export function isPart(value: unknown): value is PartRecord {
  return object(value) && nonempty(value.id) && nonempty(value.type) && nonempty(value.name)
    && stringsAt(value, ["vendor_or_brand", "brand_name", "_path"])
    && nullableAt(value, ["brand_url", "wifi_standard", "wifi_bands", "ble_version", "ieee802154_protocols", "form_factor", "price_tier", "soc_ref", "module_ref"], string)
    && nullableAt(value, ["bt_classic", "ieee802154", "usb_native"], boolean)
    && nullableAt(value, ["flash_mb", "psram_mb"], number) && sources(value.sources);
}

export function isFirmware(value: unknown): value is Firmware {
  if (!object(value) || !nonempty(value.id) || value.type !== "firmware" || !nonempty(value.name)
    || !stringsAt(value, ["url", "category"]) || !nullableAt(value, ["maintainer", "license", "manifest_url"], string)
    || ![value.distribution, value.capabilities, value.socs].every(strings) || !sources(value.sources)) return false;
  if (value.boards !== undefined && (!Number.isSafeInteger(value.boards) || (value.boards as number) < 0)) return false;
  for (const key of ["summary", "seo_title", "readme_lang", "readme_en"]) {
    if (value[key] !== undefined && !nullable(value[key], string)) return false;
  }
  if (value.popularity != null) {
    if (!object(value.popularity)) return false;
    for (const key of ["stars", "forks"]) {
      const count = value.popularity[key];
      if (count != null && (!Number.isSafeInteger(count) || (count as number) < 0)) return false;
    }
    for (const key of ["as_of", "github_as_of", "downloads_as_of", "editorial_home_as_of"]) {
      if (value.popularity[key] != null && !string(value.popularity[key])) return false;
    }
  }
  // Keep additional API fields (requires/not_required/benefits_from, etc.) on
  // the original record; never rebuild a smaller object that drops evidence.
  return true;
}

function isRecipe(value: unknown): value is Recipe {
  if (!object(value) || !nonempty(value.id) || value.type !== "recipe"
    || ![value.board, value.firmware, value.status, value.chip_family].every(nonempty)
    || !nullableAt(value, ["firmware_version", "verified_by", "verified_at", "notes"], string)
    || !sources(value.sources)) return false;
  return value.flash === null || (object(value.flash)
    && nullableAt(value.flash, ["method", "manifest_url", "bin_url", "offset", "env", "partition"], string));
}

function error(path: string, message: string): { status: "error"; message: string } {
  return { status: "error", message: `${path}: ${message}` };
}

/** Shared completeness gate for Atlas and the public sitemap. */
export function validateCatalogCollection<T extends { id: string }>(
  body: unknown, path: "/parts" | "/firmware" | "/recipes", guard: Guard<T>,
): CollectionResult<T> {
  if (!object(body) || !Array.isArray(body.results)) return error(path, "Malformed collection response.");
  if (!body.results.every(guard)) return error(path, "Malformed catalog record.");
  const records: T[] = body.results;
  if (new Set(records.map((record) => record.id)).size !== records.length) return error(path, "Duplicate record IDs.");
  const hasTotal = Object.hasOwn(body, "total");
  if (path === "/firmware" && !hasTotal) return error(path, "Missing collection total; completeness is unknown.");
  if (hasTotal && (!Number.isSafeInteger(body.total) || body.total !== records.length)) {
    return error(path, "Collection total does not match received records; completeness is unknown.");
  }
  if (path === "/parts" && records.length >= PARTS_CAP && !hasTotal) {
    return error(path, "API record cap reached; the collection may be truncated.");
  }
  return { status: "ok", records };
}

async function collection<T extends { id: string }>(
  baseUrl: string, path: "/parts" | "/firmware" | "/recipes", guard: Guard<T>, fetcher: typeof fetch, refreshKey: string | null,
): Promise<CollectionResult<T>> {
  let response: Response | undefined;
  for (const timeout of [TIMEOUT_MS, COLD_START_TIMEOUT_MS]) {
    try {
      const url = `${baseUrl.replace(/\/+$/, "")}${path}${refreshKey ? `?_atlas_refresh=${refreshKey}` : ""}`;
      response = await fetcher(url, {
        next: { revalidate: 3600, tags: [CATALOG_TAG] },
        headers: serverApiHeaders(baseUrl),
        signal: AbortSignal.timeout(timeout),
      });
      break;
    } catch {
      if (timeout === COLD_START_TIMEOUT_MS) return error(path, "API unavailable after retry.");
    }
  }
  if (!response) return error(path, "API unavailable.");
  if (!response.ok) return error(path, `HTTP ${response.status}.`);
  let body: unknown;
  try { body = await response.json(); }
  catch { return error(path, "Invalid JSON response."); }
  return validateCatalogCollection(body, path, guard);
}

/** Full collections only. An unavailable or incomplete response never becomes
 * an empty catalog or a successful partial graph. */
async function loadAtlasCatalogOnce(baseUrl: string, fetcher: typeof fetch, fresh: boolean): Promise<AtlasCatalogResult> {
  // Use one new cache key for all three collections on the rare retry. This
  // bypasses a mixed old snapshot without turning normal Atlas renders into
  // uncached cold API calls or disabling page prerendering.
  const refreshKey = fresh ? Date.now().toString(36) : null;
  const [parts, firmware, recipes] = await Promise.all([
    collection(baseUrl, "/parts", isPart, fetcher, refreshKey),
    collection(baseUrl, "/firmware", isFirmware, fetcher, refreshKey),
    collection(baseUrl, "/recipes", isRecipe, fetcher, refreshKey),
  ]);
  if (parts.status !== "ok" || firmware.status !== "ok" || recipes.status !== "ok") {
    return { status: "error", message: [parts, firmware, recipes]
      .filter((result) => result.status === "error").map((result) => result.message).join(" ") };
  }
  // The API's firmware.boards is a count of recipes at every trust tier. It
  // can expose a truncated recipes list even when that endpoint has no total.
  // Unknown firmware references stay on the catalog for the model's gap UI.
  const recipeCounts = new Map<string, number>();
  for (const recipe of recipes.records) {
    recipeCounts.set(recipe.firmware, (recipeCounts.get(recipe.firmware) ?? 0) + 1);
  }
  const mismatched = firmware.records.filter((record) =>
    record.boards !== undefined && record.boards !== (recipeCounts.get(record.id) ?? 0));
  if (mismatched.length > 0) {
    // A deploy can leave independently cached collections at different
    // revisions. Retry the entire snapshot once; a real disagreement still
    // fails closed instead of publishing a plausible partial graph.
    if (!fresh) return loadAtlasCatalogOnce(baseUrl, fetcher, true);
    return error("/recipes", `Recipe counts disagree with /firmware for ${mismatched.length} project(s); completeness is unknown.`);
  }
  return { status: "ok", catalog: { parts: parts.records, firmware: firmware.records, recipes: recipes.records } };
}

export function loadAtlasCatalog(baseUrl: string, fetcher: typeof fetch = fetch): Promise<AtlasCatalogResult> {
  return loadAtlasCatalogOnce(baseUrl, fetcher, false);
}
