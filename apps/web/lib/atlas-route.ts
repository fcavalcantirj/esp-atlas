import type { Recipe, SourceEntry } from "./api.ts";

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
/** A citation must not become an installation handoff for a broken pairing.
 * Preserve its text and verification date; documentation remains navigable. */
export function recipeSourceHref(recipe: Pick<Recipe, "status" | "flash">, source: SourceEntry): string | null {
  const href = sourceHref(source.url);
  if (!href || recipe.status !== "broken") return href;
  const url = new URL(href);
  url.hash = "";
  const recordedArtifact = [recipe.flash?.bin_url, recipe.flash?.manifest_url].some(value => {
    const artifactHref = sourceHref(value);
    if (!artifactHref) return false;
    const artifact = new URL(artifactHref);
    artifact.hash = "";
    return artifact.href === url.href;
  });
  const artifactField = /^(?:flash(?:\.(?:bin_url|manifest_url))?|distribution)$/.test(source.field);
  const artifactPath = /\.(?:bin|uf2|hex|elf|zip)(?:\.gz)?$/i.test(url.pathname);
  return recordedArtifact || artifactField || artifactPath ? null : href;
}
