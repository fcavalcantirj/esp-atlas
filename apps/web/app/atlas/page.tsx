import type { Metadata } from "next";
import { Suspense } from "react";
import AtlasExplorer from "@/components/atlas/AtlasExplorer";
import AtlasUnavailable from "@/components/atlas/AtlasUnavailable";
import { fetchAtlasCatalog } from "@/lib/atlas-server";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

export const revalidate = 300;
const description = "Explore the ESP32 catalog through silicon, hardware, firmware and cited relationships. Every recipe keeps its evidence and trust tier.";
export const metadata: Metadata = {
  title: "Explore the atlas", description,
  alternates: { canonical: "/atlas" },
  // Interactive selection URLs are a workspace; canonical record pages remain indexable.
  robots: { index: false, follow: true },
  openGraph: { type: "website", siteName: SITE_NAME, title: `Explore the atlas · ${SITE_NAME}`, description, url: "/atlas", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `Explore the atlas · ${SITE_NAME}`, description, images: [OG_IMAGE.url] },
};

export default async function AtlasPage() {
  const result = await fetchAtlasCatalog();
  return <main id="main" tabIndex={-1}>
    <Suspense fallback={<p className="container" role="status">Opening the atlas…</p>}>
      {result.status === "ok" ? <AtlasExplorer catalog={result.catalog} /> : <AtlasUnavailable />}
    </Suspense>
  </main>;
}
