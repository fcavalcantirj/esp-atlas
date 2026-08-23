import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PartResultCard from "@/components/PartResultCard";
import { fetchPartsByBrand } from "@/lib/api-server";
import type { PartRecord } from "@/lib/api";
import { typePlural } from "@/lib/format";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { brandGraph } from "@/lib/structured-data";

// Brand hub: every part the core returns for /search?brand=<slug>, server-rendered
// like the part pages. The slug is the dataset's canonical folder name
// (vendor_or_brand); an unknown slug is a 404. Display names are the slugs for
// now — editorial names belong in data/brands/ (Felipe's call).

const TYPE_ORDER = ["board", "module", "soc"];

function describe(brand: string, parts: PartRecord[]): string {
  const counts = TYPE_ORDER.map((t) => [t, parts.filter((p) => p.type === t).length] as const).filter(([, n]) => n > 0);
  const list = counts.map(([t, n]) => `${n} ${n === 1 ? t : typePlural(t).toLowerCase()}`).join(", ");
  return `${brand}: ${list} in the esp-atlas ESP32 dataset, each spec cited to an official datasheet or product page.`;
}

export async function generateMetadata({ params }: PageProps<"/brands/[brand]">): Promise<Metadata> {
  const { brand } = await params;
  const result = await fetchPartsByBrand(brand);
  if (result.status !== "ok" || result.data.results.length === 0) {
    return { title: brand, robots: { index: false, follow: true } };
  }
  const title = `${brand} — ESP32 boards and modules`;
  const description = describe(brand, result.data.results);
  const path = `/brands/${encodeURIComponent(brand)}`;
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
  const { brand } = await params;
  const result = await fetchPartsByBrand(brand);
  if (result.status === "ok" && result.data.results.length === 0) notFound();

  if (result.status !== "ok") {
    return (
      <main id="main" className="container container--narrow" tabIndex={-1}>
        <h1>{brand}</h1>
        <p className="lead">The API did not answer in time — this brand page could not be rendered. Try again in a moment.</p>
      </main>
    );
  }

  const parts = result.data.results;
  const groups = TYPE_ORDER.map((type) => ({ type, items: parts.filter((p) => p.type === type) })).filter((g) => g.items.length > 0);

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={brandGraph(brand, parts)} />
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <Link href="/brands">Brands</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">{brand}</span>
      </nav>
      <h1>{brand}</h1>
      <p className="lead">
        {parts.length} {parts.length === 1 ? "part" : "parts"} in esp-atlas from {brand} — every spec cited to an official source.
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
