// Server-side API access (server components, generateMetadata, sitemap).
//
// The browser can call the API relatively (/api) because vercel.json rewrites
// it, but the Next server needs an absolute URL. Resolution order:
//   1. API_INTERNAL_URL            explicit override (non-standard deployments)
//   2. NEXT_PUBLIC_API_URL         only if absolute (local dev: http://localhost:8000)
//   3. Vercel system env           https://<production domain or deployment URL>/api
//   4. http://localhost:8000       bare local dev
//
// Every call is bounded (3 s) and never throws: callers get a status they can
// branch on, so a cold/unreachable Python function degrades to the client-side
// fallback instead of a 500.
import type { BrandPage, Example, Facets, Firmware, PartDetail, PartRecord, Recipe } from "@/lib/api";

const REVALIDATE_SECONDS = 3600;
const TIMEOUT_MS = 3000;

function stripSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function serverApiBase(): string {
  if (process.env.API_INTERNAL_URL) return stripSlash(process.env.API_INTERNAL_URL);
  const pub = process.env.NEXT_PUBLIC_API_URL;
  if (pub && /^https?:\/\//.test(pub)) return stripSlash(pub);
  const host =
    process.env.VERCEL_ENV === "production" ? process.env.VERCEL_PROJECT_PRODUCTION_URL : process.env.VERCEL_URL;
  if (host) return `https://${host}/api`;
  return "http://localhost:8000";
}

export type ServerFetchResult<T> =
  | { status: "ok"; data: T }
  | { status: "not_found" }
  | { status: "error"; message: string };

async function serverFetch<T>(path: string): Promise<ServerFetchResult<T>> {
  try {
    const res = await fetch(`${serverApiBase()}${path}`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (res.status === 404) return { status: "not_found" };
    if (!res.ok) return { status: "error", message: `HTTP ${res.status}` };
    return { status: "ok", data: (await res.json()) as T };
  } catch (err) {
    return { status: "error", message: err instanceof Error ? err.message : String(err) };
  }
}

export function fetchPartDetail(id: string): Promise<ServerFetchResult<PartDetail>> {
  return serverFetch<PartDetail>(`/parts/${encodeURIComponent(id)}`);
}

export async function fetchAllParts(): Promise<PartRecord[]> {
  const result = await serverFetch<{ results: PartRecord[] }>(`/parts`);
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

export async function fetchFirmwareList(): Promise<ServerFetchResult<{ results: Firmware[] }>> {
  return serverFetch<{ results: Firmware[] }>(`/firmware`);
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
