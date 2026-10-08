import type { Metadata } from "next";
import BrowseSection, { type BrowseItem } from "@/components/BrowseSection";
import HomeView from "@/components/HomeView";
import JsonLd from "@/components/JsonLd";
import { fetchAllParts, fetchExamples, fetchFacets, fetchFirmwareList } from "@/lib/api-server";
import { boardsLabel, compactCount } from "@/lib/format";
import { selectPopularFirmware } from "@/lib/popular-firmware";

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
  const [facets, parts, examples, firmwareResult] = await Promise.all([
    fetchFacets(),
    fetchAllParts(),
    fetchExamples(),
    fetchFirmwareList(),
  ]);

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

  // Above-the-fold passive discovery for the home visitor who never types
  // into HomeView's search box: the API's own firmware list, ranked by cited
  // popularity (never fabricated -- selectPopularFirmware excludes anything
  // with no stars and no boards signal). A cold/empty fetch degrades to no
  // shelf, same idiom as the chip/brand sections below.
  const popularFirmware: BrowseItem[] =
    firmwareResult.status === "ok"
      ? selectPopularFirmware(firmwareResult.data.results).map((fw) => {
          const stars = fw.popularity?.stars;
          const boards = boardsLabel(fw.boards);
          const starsNote = stars != null && stars > 0 ? `★ ${compactCount(stars)}` : null;
          return {
            href: `/firmware/${encodeURIComponent(fw.id)}`,
            name: fw.name,
            note: [starsNote, boards].filter(Boolean).join(" · "),
            partId: fw.id,
            partType: "firmware",
          };
        })
      : [];

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={homeGraph()} />
      <div className="home-intro">
        <h1>What do you want to build with ESP32?</h1>
        <p>
          Every ESP32 SoC, module and dev board in one place, every spec cited to an official datasheet. Say what you
          want to build or run and get the parts that fit — nothing guessed, nothing invented.
        </p>
      </div>
      <HomeView examples={examples.status === "ok" ? examples.data.results : []} />
      <BrowseSection
        id="browse-firmware"
        title="Popular firmware"
        hint="The most-starred flashable projects in the atlas, with the boards they're verified to run on."
        items={popularFirmware}
        origin="popular_firmware"
      />
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
