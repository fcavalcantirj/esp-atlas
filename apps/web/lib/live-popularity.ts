import type { Firmware } from "./api.ts";

export type PopularityRecord = Pick<Firmware, "id" | "url" | "popularity" | "sources">;
export type PopularityIdentity = { firmwareId: string; sourceUrl: string; repoId: number; catalogTime: number };
type Observation = { stars: number; forks: number; observed_at: string; source_url: string; repo_id: number };
export type LivePopularity =
  | { outcome: "fresh" | "cached" | "stale"; github: Observation }
  | { outcome: "unavailable" | "ineligible"; github: null };

const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

// Date.parse alone normalizes impossible dates. Reject them before comparing;
// a date-only catalog observation covers the whole UTC day, not its first second.
function timestamp(value: unknown, dateOnly = false): number | null {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2}))?$/.exec(value);
  if (!match || (!dateOnly && !match[4])) return null;
  const [, year, month, day, hour, minute, second, zone] = match;
  const calendar = new Date(`${year}-${month}-${day}T00:00:00Z`);
  if (!Number.isFinite(calendar.getTime()) || calendar.toISOString().slice(0, 10) !== value.slice(0, 10)) return null;
  if (hour && (+hour > 23 || +minute > 59 || +second > 59)) return null;
  if (zone && zone !== "Z" && (+zone.slice(1, 3) > 23 || +zone.slice(4) > 59)) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed + (hour ? 0 : 86_399_999) : null;
}

export function popularityIdentity(record: PopularityRecord): PopularityIdentity | null {
  const { id, url, popularity, sources } = record;
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id) || !/^https:\/\/github\.com\/[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(url) || /\/(?:\.|\.\.)$/.test(url) || url.endsWith(".git")) return null;
  const repoId = popularity?.github_repo_id;
  const catalogTime = timestamp(popularity?.github_as_of, true);
  if (!count(repoId) || repoId === 0 || catalogTime === null || !Array.isArray(sources)) return null;
  if (!["popularity.github_repo_id", "popularity.github_as_of"].every(field => sources.some(s => s.field === field && s.url === url && timestamp(s.verified, true) !== null))) return null;
  return { firmwareId: id, sourceUrl: url, repoId, catalogTime };
}

/** Untrusted optional overlay. A rejected payload leaves the rendered catalog intact. */
export function readLivePopularity(payload: unknown, identity: PopularityIdentity, now = Date.now()): LivePopularity | null {
  if (!object(payload) || payload.firmware_id !== identity.firmwareId || !object(payload.catalog)) return null;
  if (payload.retry_after_seconds != null && !count(payload.retry_after_seconds)) return null;
  const { outcome, github, catalog } = payload;
  if (outcome === "unavailable" || outcome === "ineligible") return github === null ? { outcome, github: null } : null;
  if (outcome !== "fresh" && outcome !== "cached" && outcome !== "stale") return null;
  if (!object(github) || !count(github.stars) || !count(github.forks)) return null;
  if (github.source_url !== identity.sourceUrl || github.repo_id !== identity.repoId ||
      catalog.source_url !== identity.sourceUrl || catalog.repo_id !== identity.repoId) return null;
  const observed = timestamp(github.observed_at);
  const catalogTime = timestamp(catalog.github_as_of, true);
  if (observed === null || catalogTime === null || !Number.isFinite(now) || observed > now + 60_000 ||
      observed <= Math.max(identity.catalogTime, catalogTime)) return null;
  return { outcome, github: { stars: github.stars, forks: github.forks, observed_at: github.observed_at as string,
    source_url: identity.sourceUrl, repo_id: identity.repoId } };
}

/** Bound bytes as well as time. The caller's AbortSignal bounds the whole fetch/body read. */
export async function popularityResponse(response: Response): Promise<unknown> {
  const limit = 16 * 1024;
  if (!response.ok || !response.body || Number(response.headers.get("content-length")) > limit) {
    await response.body?.cancel();
    return null;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0, text = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) { await reader.cancel(); return null; }
      text += decoder.decode(value, { stream: true });
    }
    return JSON.parse(text + decoder.decode()) as unknown;
  } finally { reader.releaseLock(); }
}
