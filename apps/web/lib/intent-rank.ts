// Pure as-you-type ranking over the real firmware list for the home hero's
// secondary intent box ("…or tell us what you want to build"). No fetch, no
// DOM -- lib/intent-rank.test.ts exercises it directly; the component only
// renders what this returns.
import type { Firmware } from "@/lib/api";

const WORD_SPLIT = /\s+/;
const NAME_WEIGHT = 3;
const FIELD_WEIGHT = 1;

function haystack(firmware: Firmware): string {
  return [firmware.name, firmware.summary ?? "", firmware.category, ...firmware.capabilities, ...firmware.socs]
    .join(" ")
    .toLowerCase();
}

/**
 * Scores one firmware against a query: each query word scores NAME_WEIGHT when
 * it hits the name, FIELD_WEIGHT when it only hits the summary/category/
 * capabilities/socs, and nothing when it hits neither. 0 means no query word
 * matched anything cited about this firmware -- never a fabricated match.
 */
export function scoreFirmware(firmware: Firmware, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const words = q.split(WORD_SPLIT).filter(Boolean);
  const name = firmware.name.toLowerCase();
  const hay = haystack(firmware);
  let score = 0;
  for (const word of words) {
    if (name.includes(word)) score += NAME_WEIGHT;
    else if (hay.includes(word)) score += FIELD_WEIGHT;
  }
  return score;
}

export const DEFAULT_INTENT_LIMIT = 6;

/**
 * Ranks `firmware` for an as-you-type intent query: highest score first, tied
 * firmware broken by cited stars desc then name A→Z for stable ordering.
 * Firmware that scores 0 (nothing matched) is excluded, never padded in.
 */
export function rankByIntent(firmware: Firmware[], query: string, limit: number = DEFAULT_INTENT_LIMIT): Firmware[] {
  if (!query.trim()) return [];
  return firmware
    .map((item) => ({ item, score: scoreFirmware(item, query) }))
    .filter((entry) => entry.score > 0)
    .sort(
      (a, b) =>
        b.score - a.score ||
        (b.item.popularity?.stars ?? 0) - (a.item.popularity?.stars ?? 0) ||
        a.item.name.localeCompare(b.item.name),
    )
    .slice(0, limit)
    .map((entry) => entry.item);
}
