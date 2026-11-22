// Server-side API access (server components, generateMetadata, sitemap).
//
// The browser can call the API relatively (/api) because vercel.json rewrites
// it, but the Next server needs an absolute URL. Resolution order:
//   1. API_INTERNAL_URL            explicit override (non-standard deployments)
//   2. NEXT_PUBLIC_API_URL         only if absolute (local dev: http://localhost:8000)
//   3. Vercel system env           https://<this deployment's own URL>/api, with the project's automation
//                                  bypass (Vercel injects VERCEL_AUTOMATION_BYPASS_SECRET into every
//                                  deployment); production falls back to its alias only when that secret is
//                                  missing, because the own *.vercel.app URL is protected
//   4. http://localhost:8000       bare local dev
//
// Why the OWN deployment (2026-11-22, Jr redesign plan step 1): Vercel's Data Cache survives deployments and
// is keyed by URL. Reading through the production alias let a new deployment render pages from the previous
// deployment's API; the own URL makes every cache key deployment-specific. No catalog read happens during
// `next build` (the deployment's own API does not exist yet), and no catalog fetch follows a redirect, so the
// bypass header can never reach another host.
//
// Every call is bounded (3 s) and never throws: callers get a status they can
// branch on, so a cold/unreachable Python function degrades to the client-side
// fallback instead of a 500.
import type { BrandPage, Example, Facets, Firmware, PartDetail, PartRecord, Recipe } from "@/lib/api";
import { DEFAULT_SORT } from "./firmware-sort.ts";
import { apiQueryString, type FirmwareFacets, type FirmwareQuery } from "./firmware-filters.ts";
import type { BootBoard } from "@/lib/troubleshooter";

const REVALIDATE_SECONDS = 3600;
// Every server fetch is tagged so a deletion can be purged on demand (POST /api/revalidate)
// instead of lingering in the Data Cache until the next revalidation -- which, for a deleted
// record, 404s and leaves the stale entry in place ("ghost pages"). `cache: "no-store"` is
// NOT the fix: it was tried (0c8ce8c) and reverted (9a3a614) because it sent every render to a
// cold Python function that rebuilds its SQLite index at import.
export const CATALOG_TAG = "catalog";
export const POPULARITY_TAG = "popularity";

/** Metrics-bearing responses keep catalog eviction and a shorter independent TTL. */
export function catalogCachePolicy(path: string): { revalidate: number; tags: string[] } {
  const pathname = path.split("?")[0];
  return pathname === "/examples" || pathname === "/firmware" || pathname.startsWith("/firmware/")
    ? { revalidate: 240, tags: [CATALOG_TAG, POPULARITY_TAG] }
    : { revalidate: REVALIDATE_SECONDS, tags: [CATALOG_TAG] };
}
// The API is a serverless Python function that boots an interpreter, imports
// FastAPI/pydantic/jsonschema and builds the SQLite index before it can answer.
// Warm, that is well under a second; cold, it is seconds -- and a fresh deploy
// or a low-traffic preview is always cold, which is when a human is most likely
// to be looking. One short attempt keeps a warm-but-broken API failing fast; the
// retry, with a longer budget, is what a cold start actually needs, and the
// first attempt has already begun warming the function.
const TIMEOUT_MS = 3000;
const COLD_START_TIMEOUT_MS = 9000;

function stripSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function serverApiBase(): string {
  if (process.env.API_INTERNAL_URL) return stripSlash(process.env.API_INTERNAL_URL);
  const pub = process.env.NEXT_PUBLIC_API_URL;
  if (pub && /^https?:\/\//.test(pub)) return stripSlash(pub);
  const own = process.env.VERCEL_URL;
  if (process.env.VERCEL_ENV === "production") {
    if (own && process.env.VERCEL_AUTOMATION_BYPASS_SECRET) return `https://${own}/api`;
    const alias = process.env.VERCEL_PROJECT_PRODUCTION_URL;
    if (alias) return `https://${alias}/api`;
  }
  if (own) return `https://${own}/api`;
  return "http://localhost:8000";
}

/** A deployment's own URL is protected (the project protects everything but its custom domain), so its
 * server-side reads of its own API carry the automation bypass Vercel injects into every deployment. The
 * header goes to exactly that origin — https://$VERCEL_URL/api — and nowhere else: never to the alias,
 * API_INTERNAL_URL, NEXT_PUBLIC_API_URL or another host. */
export function serverApiHeaders(base = serverApiBase()): HeadersInit | undefined {
  const deployment = process.env.VERCEL_URL;
  const secret = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
  const env = process.env.VERCEL_ENV;
  if ((env !== "preview" && env !== "production") || !deployment || !secret) return undefined;
  if (base !== `https://${deployment}/api`) return undefined;
  return { "x-vercel-protection-bypass": secret };
}

/** `next build` renders whatever it can, but the deployment's own API is not running yet: a catalog read
 * then would reach an old deployment or nothing. Every catalog helper answers "unavailable" without touching
 * the network during the build; pages fill in at runtime from their own deployment. */
export function isBuildPhase(): boolean {
  return process.env.NEXT_PHASE === "phase-production-build";
}

export type ServerFetchResult<T> =
  | { status: "ok"; data: T }
  | { status: "not_found" }
  | { status: "error"; message: string };

async function attempt<T>(path: string, timeoutMs: number): Promise<ServerFetchResult<T>> {
  const base = serverApiBase();
  const res = await fetch(`${base}${path}`, {
    next: catalogCachePolicy(path),
    headers: serverApiHeaders(base),
    redirect: "error",          // a redirect would carry the bypass header to wherever it points
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 404) return { status: "not_found" };
  if (!res.ok) return { status: "error", message: `HTTP ${res.status}` };
  return { status: "ok", data: (await res.json()) as T };
}

async function serverFetch<T>(path: string): Promise<ServerFetchResult<T>> {
  if (isBuildPhase()) return { status: "error", message: "build phase: the catalog is read at runtime" };
  try {
    return await attempt<T>(path, TIMEOUT_MS);
  } catch {
    // Only a timeout or a transport failure reaches here — an HTTP status,
    // including 404, already returned above and is never retried.
    try {
      return await attempt<T>(path, COLD_START_TIMEOUT_MS);
    } catch (err) {
      return { status: "error", message: err instanceof Error ? err.message : String(err) };
    }
  }
}

/** For the ISR detail pages (generateStaticParams): whatever they render is cached and served until
 * the next revalidation, so a degraded render (a section missing, an "API did not answer" shell) must
 * throw instead. A thrown render is never stored: Next keeps serving the last good page and retries on
 * the next request (Next docs, Incremental Static Regeneration, "Handling uncaught exceptions"). */
export function dataOrThrow<T>(result: ServerFetchResult<T>, what: string): T {
  if (result.status === "ok") return result.data;
  throw new Error(`${what} unavailable: ${result.status === "error" ? result.message : "not found"}`);
}

export function fetchPartDetail(id: string): Promise<ServerFetchResult<PartDetail>> {
  return serverFetch<PartDetail>(`/parts/${encodeURIComponent(id)}`);
}

export function fetchAllPartsResult(): Promise<ServerFetchResult<{ results: PartRecord[] }>> {
  return serverFetch<{ results: PartRecord[] }>(`/parts`);
}

export async function fetchAllParts(): Promise<PartRecord[]> {
  const result = await fetchAllPartsResult();
  return result.status === "ok" ? result.data.results : [];
}

export function fetchFacets(): Promise<ServerFetchResult<Facets>> {
  return serverFetch<Facets>(`/facets`);
}

/** /examples: the generated home examples; a cold API degrades to an empty list
 * at the call site, mirroring the browse sections. */
export function fetchExamples(): Promise<ServerFetchResult<{ results: Example[] }>> {
  return serverFetch<{ results: Example[] }>(`/examples`);
}

/** /brands/<slug>: the brand's editorial name/url plus every part from it (core's
 * exact brand filter); an unknown slug is an empty `results` list, not an error. */
export function fetchBrandPage(slug: string): Promise<ServerFetchResult<BrandPage>> {
  return serverFetch<BrandPage>(`/brands/${encodeURIComponent(slug)}`);
}

/** SPEC-firmware-ordering.md §3: `sort` is only sent when it differs from the
 * API's own default, so the default request stays byte-identical to before
 * this mode existed. */
export async function fetchFirmwareList(sort?: string): Promise<ServerFetchResult<{ results: Firmware[] }>> {
  const query = sort && sort !== DEFAULT_SORT ? `?sort=${encodeURIComponent(sort)}` : "";
  return serverFetch<{ results: Firmware[] }>(`/firmware${query}`);
}

/** SPEC-firmware-search.md: the searched/filtered list. With nothing set the request is the bare `/firmware`,
 * byte-identical to fetchFirmwareList(), so the default page hits the same cached response as before. */
export async function fetchFirmwareSearch(
  query: FirmwareQuery,
): Promise<ServerFetchResult<{ results: Firmware[]; total: number; catalog_total?: number | null }>> {
  return serverFetch<{ results: Firmware[]; total: number; catalog_total?: number | null }>(`/firmware${apiQueryString(query)}`);
}

export function fetchFirmwareFacets(): Promise<ServerFetchResult<FirmwareFacets>> {
  return serverFetch<FirmwareFacets>("/firmware/facets");
}

export function fetchFirmware(id: string): Promise<ServerFetchResult<Firmware>> {
  return serverFetch<Firmware>(`/firmware/${encodeURIComponent(id)}`);
}

export function fetchRecipesForBoard(boardId: string): Promise<ServerFetchResult<{ results: Recipe[] }>> {
  return serverFetch<{ results: Recipe[] }>(`/recipes?board=${encodeURIComponent(boardId)}`);
}

export function fetchRecipesForFirmware(firmwareId: string): Promise<ServerFetchResult<{ results: Recipe[] }>> {
  return serverFetch<{ results: Recipe[] }>(`/recipes?firmware=${encodeURIComponent(firmwareId)}`);
}

/** /boards/boot: boards that cite a download_mode, for the /debug connect
 * troubleshooter. A cold/unreachable API degrades to an empty list — the page
 * still renders, the troubleshooter just falls back to the generic sequence. */
export async function fetchBootBoards(): Promise<BootBoard[]> {
  const result = await serverFetch<BootBoard[]>(`/boards/boot`);
  return result.status === "ok" ? result.data : [];
}
