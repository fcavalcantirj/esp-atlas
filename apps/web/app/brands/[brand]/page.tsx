import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PartResultCard from "@/components/PartResultCard";
import { dataOrThrow, fetchBrandPage } from "@/lib/api-server";
import type { PartRecord } from "@/lib/api";
import { typePlural } from "@/lib/format";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { brandGraph } from "@/lib/structured-data";

// Render each detail page on its first visit, then serve it from the cache (ISR) instead of rendering
// every request (2026-11-18: these routes were dynamic, `cache-control: private, no-store`, x-vercel-cache
// MISS on every hit). No path is pre-rendered at build (an empty list): the catalog API is not reachable
// during a Vercel build, and a cold first render is the same as today's every render. The data fetches keep
// their own revalidate and `catalog`/`popularity` tags, so POST /api/revalidate still purges these pages.
export function generateStaticParams() {
  return [];
}

// Brand hub: the brand's editorial identity (data/brands/<slug>/brand.md) plus
// every part the core returns for it, server-rendered like the part pages. The
// slug in the URL is the dataset's canonical folder name (vendor_or_brand); an
// unknown slug is a 404. The display name always comes from the API — this
// component only renders what GET /brands/<slug> returns.

const TYPE_ORDER = ["board", "module", "soc"];

function describe(name: string, parts: PartRecord[]): string {
  const counts = TYPE_ORDER.map((t) => [t, parts.filter((p) => p.type === t).length] as const).filter(([, n]) => n > 0);
  const list = counts.map(([t, n]) => `${n} ${n === 1 ? t : typePlural(t).toLowerCase()}`).join(", ");
  return `${name}: ${list} in the esp-atlas ESP32 dataset, each spec cited to an official datasheet or product page.`;
}

export async function generateMetadata({ params }: PageProps<"/brands/[brand]">): Promise<Metadata> {
  const { brand: slug } = await params;
  const page = dataOrThrow(await fetchBrandPage(slug), `Brand API for ${slug}`);
  if (page.results.length === 0) {
    return { title: slug, robots: { index: false, follow: true } };
  }
  const name = page.brand.name;
  const title = `${name} — ESP32 boards and modules`;
  const description = describe(name, page.results);
  const path = `/brands/${encodeURIComponent(slug)}`;
  // Nested metadata objects replace the root ones wholesale (see the part page).
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", siteName: SITE_NAME, title, description, url: path, images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title, description, images: [OG_IMAGE.url] },
  };
}

export default async function BrandPage({ params }: PageProps<"/brands/[brand]">) {
  const { brand: slug } = await params;
  // A cold or unreachable API throws (the ISR cache would otherwise keep an "API did not answer" page).
  const { brand, results: parts } = dataOrThrow(await fetchBrandPage(slug), `Brand API for ${slug}`);
  if (parts.length === 0) notFound();

  const groups = TYPE_ORDER.map((type) => ({ type, items: parts.filter((p) => p.type === type) })).filter((g) => g.items.length > 0);

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={brandGraph(slug, brand.name, parts)} />
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <Link href="/brands">Brands</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">{brand.name}</span>
      </nav>
      <h1>{brand.name}</h1>
      <p className="lead">
        {parts.length} {parts.length === 1 ? "part" : "parts"} in esp-atlas from {brand.name} — every spec cited to an official source.
      </p>
      {groups.map((group) => (
        <section key={group.type} className="brand-group" aria-labelledby={`brand-${group.type}`}>
          <h2 id={`brand-${group.type}`}>
            {typePlural(group.type)} ({group.items.length})
          </h2>
          <ul className="results-list">
            {group.items.map((record, index) => (
              <PartResultCard key={record.id} part={record} origin="brand" position={index + 1} />
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
