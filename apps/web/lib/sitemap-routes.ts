import type { MetadataRoute } from "next";

// The sitemap's always-present static content pages -- unlike app/sitemap.ts's
// catalog-driven entries (parts, firmware, brands, the typed indexes), these
// never depend on what the API returns, so the list is kept here, pure, and
// unit-tested directly instead of only through a full sitemap() run.
export function staticContentRoutes(siteUrl: string, newest: string | undefined): MetadataRoute.Sitemap {
  return [
    { url: `${siteUrl}/`, lastModified: newest, changeFrequency: "daily", priority: 1 },
    { url: `${siteUrl}/wizard`, lastModified: newest, changeFrequency: "weekly", priority: 0.8 },
    { url: `${siteUrl}/how-we-work`, changeFrequency: "monthly", priority: 0.5 },
    { url: `${siteUrl}/submit`, changeFrequency: "monthly", priority: 0.5 },
  ];
}
