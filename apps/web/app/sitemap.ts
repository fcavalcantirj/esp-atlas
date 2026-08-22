import type { MetadataRoute } from "next";
import { fetchAllParts } from "@/lib/api-server";
import { SITE_URL } from "@/lib/site";

// Rendered on request (never at build time — the Python API is not running
// during `next build`); the /parts fetch underneath is cached for an hour.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, changeFrequency: "daily", priority: 1 },
    { url: `${SITE_URL}/compare`, changeFrequency: "weekly", priority: 0.6 },
  ];

  const parts = await fetchAllParts();
  const partRoutes: MetadataRoute.Sitemap = parts.map((part) => ({
    url: `${SITE_URL}/parts/${encodeURIComponent(part.id)}`,
    changeFrequency: "weekly",
    priority: part.type === "board" ? 0.8 : 0.7,
  }));

  return [...staticRoutes, ...partRoutes];
}
