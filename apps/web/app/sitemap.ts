import type { MetadataRoute } from "next";
import { fetchAllParts } from "@/lib/api-server";
import type { PartRecord } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

// Rendered on request (never at build time — the Python API is not running
// during `next build`); the /parts fetch underneath is cached for an hour.
export const dynamic = "force-dynamic";

// A record's last change, as far as the dataset knows it: the newest date any
// of its sources was verified (YYYY-MM-DD). Google uses <lastmod> only when it
// stays accurate, so this is never bumped artificially.
function lastVerified(part: PartRecord): string | undefined {
  const dates = part.sources.map((s) => s.verified).filter(Boolean).sort();
  return dates.length ? dates[dates.length - 1] : undefined;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const parts = await fetchAllParts();

  const partRoutes: MetadataRoute.Sitemap = parts.map((part) => ({
    url: `${SITE_URL}/parts/${encodeURIComponent(part.id)}`,
    lastModified: lastVerified(part),
    changeFrequency: "weekly",
    priority: part.type === "board" ? 0.8 : 0.7,
  }));

  const newest = partRoutes
    .map((r) => r.lastModified)
    .filter((d): d is string => typeof d === "string")
    .sort()
    .pop();

  // /compare is noindex (a client-rendered tool), so it is no longer listed here.
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, lastModified: newest, changeFrequency: "daily", priority: 1 },
  ];

  return [...staticRoutes, ...partRoutes];
}
