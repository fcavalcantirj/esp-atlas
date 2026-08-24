import type { Metadata } from "next";
import BrowseSection, { type BrowseItem } from "@/components/BrowseSection";
import HomeView from "@/components/HomeView";
import JsonLd from "@/components/JsonLd";
import { fetchAllParts, fetchExamples, fetchFacets } from "@/lib/api-server";

import { homeGraph } from "@/lib/structured-data";

// Incremental static: the example chips and the browse links below the wizard
// are rendered from the
// API's examples, facets (counts) and part list (names), all cached underneath, and the
// page is regenerated every five minutes. At build time the API is not running,
// so the first static render omits the section; the first request after deploy
// fills it in. Nothing here throws — a cold API degrades to "no browse links".
export const revalidate = 300;

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

function pluralParts(n: number, where: string): string {
  return `${n} ${n === 1 ? "part" : "parts"} ${where}`;
}

export default async function Home() {
  const [facets, parts, examples] = await Promise.all([fetchFacets(), fetchAllParts(), fetchExamples()]);

  // /facets.soc_ref is the core's count per chip (the chip's own record and its
  // modules included — hence "parts", never "boards"), already sorted by count;
  // the part list supplies the display name for each id.
  const socName = new Map(parts.filter((p) => p.type === "soc").map((p) => [p.id, p.name]));
  const chips: BrowseItem[] =
    facets.status === "ok"
      ? facets.data.soc_ref
          .filter((f) => socName.has(f.value))
          .map((f) => ({
            href: `/parts/${encodeURIComponent(f.value)}`,
            name: socName.get(f.value)!,
            note: pluralParts(f.count, "on this chip"),
            partId: f.value,
            partType: "soc",
          }))
      : [];

  // /facets.vendor_or_brand → the brand hubs (F5); counts are the core's.
  const brands: BrowseItem[] =
    facets.status === "ok"
      ? facets.data.vendor_or_brand.map((f) => ({
          href: `/brands/${encodeURIComponent(f.value)}`,
          name: f.display_name,
          note: pluralParts(f.count, "from this brand"),
          partId: f.value,
          partType: "brand",
        }))
      : [];

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={homeGraph()} />
      <div className="home-intro">
        <h1>What do you want to build?</h1>
        <p>
          Every ESP32 SoC, module and dev board in one place, every spec cited to an official datasheet. Say what you
          want to build or run and get the parts that fit — nothing guessed, nothing invented.
        </p>
      </div>
      <HomeView examples={examples.status === "ok" ? examples.data.results : []} />
      <BrowseSection
        id="browse-chip"
        title="Browse by chip"
        hint="Every SoC in the atlas, with the modules and boards built on it."
        items={chips}
        origin="browse"
      />
      <BrowseSection
        id="browse-brand"
        title="Browse by brand"
        hint="Every vendor and brand in the atlas, with the boards and modules they make."
        items={brands}
        origin="brand"
      />
    </main>
  );
}
