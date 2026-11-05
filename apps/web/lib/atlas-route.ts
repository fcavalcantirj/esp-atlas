export const ATLAS_LENSES = ["map", "silicon", "hardware", "firmware", "projects", "evidence"] as const;
export type AtlasLens = (typeof ATLAS_LENSES)[number];

export function atlasLens(value: string | null): AtlasLens {
  return ATLAS_LENSES.includes(value as AtlasLens) ? value as AtlasLens : "map";
}

/** Change presentation or selection without losing the other endpoint or goal. */
export function atlasHref(current: string, patch: Record<string, string | null>): string {
  const params = new URLSearchParams(current);
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === "") params.delete(key);
    else params.set(key, value);
  }
  return `/atlas${params.size ? `?${params}` : ""}`;
}

export function sourceHref(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}
