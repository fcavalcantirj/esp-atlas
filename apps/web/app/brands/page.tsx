import type { Metadata } from "next";
import Link from "next/link";
import BrowseSection, { type BrowseItem } from "@/components/BrowseSection";
import JsonLd from "@/components/JsonLd";
import { fetchFacets } from "@/lib/api-server";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { brandsIndexGraph } from "@/lib/structured-data";

// Index of every vendor/brand in the dataset, from the API's facets (the counts
// are the core's). Incremental static like "/": regenerated every five minutes,
// so the build-time render (API not running → empty list, noindex) is replaced
// within minutes of the first request. The fetch never throws.
export const revalidate = 300;

const TITLE = "ESP32 boards and modules by brand";
const DESCRIPTION =
  "Every vendor and brand in the esp-atlas dataset — Espressif, Adafruit, M5Stack, LILYGO, Seeed and more — with their datasheet-verified ESP32 boards and modules.";

export async function generateMetadata(): Promise<Metadata> {
  const facets = await fetchFacets();
  return {
    title: TITLE,
    description: DESCRIPTION,
    alternates: { canonical: "/brands" },
    // A cold API must not get an empty index cached by a crawler.
    robots: facets.status === "ok" ? undefined : { index: false, follow: true },
    openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/brands", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
  };
}

export default async function BrandsPage() {
  const facets = await fetchFacets();
  const brands = facets.status === "ok" ? facets.data.vendor_or_brand : [];
  const items: BrowseItem[] = brands.map((b) => ({
    href: `/brands/${encodeURIComponent(b.value)}`,
    name: b.value,
    note: `${b.count} ${b.count === 1 ? "part" : "parts"}`,
    partId: b.value,
    partType: "brand",
  }));

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      {brands.length > 0 && <JsonLd data={brandsIndexGraph(brands)} />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Brands</span>
      </nav>
      <h1>Brands</h1>
      <p className="lead">
        {brands.length > 0
          ? `${brands.length} vendors and brands, ${brands.reduce((n, b) => n + b.count, 0)} parts — every spec cited to an official source.`
          : "The brand list could not be loaded right now — try again in a moment."}
      </p>
      <BrowseSection id="brands" title="All brands" hint="Sorted by how many parts each one has in the atlas." items={items} origin="brand" />
    </main>
  );
}
