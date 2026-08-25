import type { MetadataRoute } from "next";
import { fetchAllParts, fetchFirmwareList } from "@/lib/api-server";
import type { SourceEntry } from "@/lib/api";
import { SITE_URL } from "@/lib/site";

// Rendered on request (never at build time — the Python API is not running
// during `next build`); the /parts and /firmware fetches underneath are each
// cached for an hour.
export const dynamic = "force-dynamic";

// A record's last change, as far as the dataset knows it: the newest date any
// of its sources was verified (YYYY-MM-DD). Google uses <lastmod> only when it
// stays accurate, so this is never bumped artificially.
function lastVerified(record: { sources: SourceEntry[] }): string | undefined {
  const dates = record.sources.map((s) => s.verified).filter(Boolean).sort();
  return dates.length ? dates[dates.length - 1] : undefined;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [parts, firmwareResult] = await Promise.all([fetchAllParts(), fetchFirmwareList()]);
  const firmware = firmwareResult.status === "ok" ? firmwareResult.data.results : [];

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

  // One hub per vendor/brand slug found in the records, dated by its newest part.
  const byBrand = new Map<string, string | undefined>();
  for (const part of parts) {
    const current = byBrand.get(part.vendor_or_brand);
    const mine = lastVerified(part);
    if (!byBrand.has(part.vendor_or_brand) || (mine && (!current || mine > current))) byBrand.set(part.vendor_or_brand, mine);
  }
  const brandRoutes: MetadataRoute.Sitemap = [...byBrand.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([brand, lastModified]) => ({
      url: `${SITE_URL}/brands/${encodeURIComponent(brand)}`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.6,
    }));

  const firmwareRoutes: MetadataRoute.Sitemap = firmware.map((fw) => ({
    url: `${SITE_URL}/firmware/${encodeURIComponent(fw.id)}`,
    lastModified: lastVerified(fw),
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  // /compare is noindex (a client-rendered tool), so it is no longer listed here.
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, lastModified: newest, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/wizard`, lastModified: newest, changeFrequency: "weekly", priority: 0.8 },
    ...(brandRoutes.length ? [{ url: `${SITE_URL}/brands`, lastModified: newest, changeFrequency: "weekly" as const, priority: 0.6 }] : []),
    // The typed indexes behind every part page's middle breadcrumb.
    ...(["/boards", "/modules", "/socs"] as const)
      .filter((path) => parts.some((p) => p.type === path.slice(1, -1)))
      .map((path) => ({ url: `${SITE_URL}${path}`, lastModified: newest, changeFrequency: "weekly" as const, priority: 0.6 })),
    ...(firmwareRoutes.length ? [{ url: `${SITE_URL}/firmware`, changeFrequency: "weekly" as const, priority: 0.6 }] : []),
  ];

  return [...staticRoutes, ...brandRoutes, ...firmwareRoutes, ...partRoutes];
}
