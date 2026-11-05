import type { MetadataRoute } from "next";
import { fetchAllPartsResult, fetchFirmwareList } from "@/lib/api-server";
import { SITE_URL } from "@/lib/site";
import { staticContentRoutes } from "@/lib/sitemap-routes";

// Rendered on request (never at build time — the Python API is not running
// during `next build`); the /parts and /firmware fetches underneath are each
// cached for an hour.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [partsResult, firmwareResult] = await Promise.all([fetchAllPartsResult(), fetchFirmwareList()]);
  if (partsResult.status !== "ok" || firmwareResult.status !== "ok") {
    throw new Error("Catalog API unavailable; refusing to publish an incomplete sitemap");
  }
  const parts = partsResult.data.results;
  const firmware = firmwareResult.data.results;
  if (parts.length === 0 || firmware.length === 0) {
    throw new Error("Catalog API returned an empty collection; refusing to publish an incomplete sitemap");
  }

  const partRoutes: MetadataRoute.Sitemap = parts.map((part) => ({
    url: `${SITE_URL}/parts/${encodeURIComponent(part.id)}`,
    changeFrequency: "weekly",
    priority: part.type === "board" ? 0.8 : 0.7,
  }));

  // One hub per vendor/brand slug found in the records.
  const brands = [...new Set(parts.map((part) => part.vendor_or_brand))];
  const brandRoutes: MetadataRoute.Sitemap = brands
    .sort((a, b) => a.localeCompare(b))
    .map((brand) => ({
      url: `${SITE_URL}/brands/${encodeURIComponent(brand)}`,
      changeFrequency: "weekly",
      priority: 0.6,
    }));

  const firmwareRoutes: MetadataRoute.Sitemap = firmware.map((fw) => ({
    url: `${SITE_URL}/firmware/${encodeURIComponent(fw.id)}`,
    changeFrequency: "weekly",
    priority: 0.6,
  }));

  // /compare is noindex (a client-rendered tool), so it is no longer listed here.
  const staticRoutes: MetadataRoute.Sitemap = [
    ...staticContentRoutes(SITE_URL),
    ...(brandRoutes.length ? [{ url: `${SITE_URL}/brands`, changeFrequency: "weekly" as const, priority: 0.6 }] : []),
    // The typed indexes behind every part page's middle breadcrumb.
    ...(["/boards", "/modules", "/socs"] as const)
      .filter((path) => parts.some((p) => p.type === path.slice(1, -1)))
      .map((path) => ({ url: `${SITE_URL}${path}`, changeFrequency: "weekly" as const, priority: 0.6 })),
    ...(firmwareRoutes.length ? [{ url: `${SITE_URL}/firmware`, changeFrequency: "weekly" as const, priority: 0.6 }] : []),
  ];

  return [...staticRoutes, ...brandRoutes, ...firmwareRoutes, ...partRoutes];
}
