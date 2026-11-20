import type { Metadata } from "next";
import Link from "next/link";
import FirmwareBrowseList from "@/components/FirmwareBrowseList";
import FirmwareFilters from "@/components/FirmwareFilters";
import JsonLd from "@/components/JsonLd";
import { fetchFirmwareFacets, fetchFirmwareSearch } from "@/lib/api-server";
import { apiQueryString, effectiveSort, emptyCopy, filteredLead, firmwareListRobots, isFiltered, parseFirmwareQuery } from "@/lib/firmware-filters";
import { firmwareLeadCopy } from "@/lib/firmware-sort";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { firmwareIndexGraph } from "@/lib/structured-data";

// Index of every firmware in the dataset, from GET /firmware. Incremental
// static like /brands: regenerated every five minutes, so a cold build-time
// render (API not running -> empty list, noindex) clears within minutes of
// the first request. The fetch never throws.
export const revalidate = 300;

const TITLE = "ESP32 firmware — what runs on what";
const DESCRIPTION =
  "Every flashable ESP32 firmware project in the esp-atlas dataset — Marauder, NEMO, Launcher and more — cited to its own repo, with the boards it has recipes for and each recipe's trust tier.";

export async function generateMetadata({ searchParams }: PageProps<"/firmware">): Promise<Metadata> {
  const query = parseFirmwareQuery(await searchParams);
  const result = await fetchFirmwareSearch(query);
  return {
    title: TITLE,
    description: DESCRIPTION,
    // SPEC-firmware-ordering.md §3 / SPEC-firmware-search.md §3: every order, search and filter canonicalizes
    // to the bare index, so none of them becomes an indexable near-duplicate.
    alternates: { canonical: "/firmware" },
    robots: firmwareListRobots(query, result.status === "ok"),
    openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/firmware", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
  };
}

export default async function FirmwareIndexPage({ searchParams }: PageProps<"/firmware">) {
  const query = parseFirmwareQuery(await searchParams);
  const [result, facetsResult] = await Promise.all([fetchFirmwareSearch(query), fetchFirmwareFacets()]);
  // Already filtered and ordered server-side by the API -- SPEC-firmware-ordering.md §1 and
  // SPEC-firmware-search.md (Golden Rule 3: the API decides, this page only renders what it returns).
  const ok = result.status === "ok";
  const firmware = ok ? result.data.results : [];
  const facets = facetsResult.status === "ok" ? facetsResult.data : null;
  const filtered = isFiltered(query);
  const catalogTotal = (ok ? result.data.catalog_total : null) ?? facets?.catalog_total ?? null;
  const sort = effectiveSort(query);

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      {firmware.length > 0 && !filtered && <JsonLd data={firmwareIndexGraph(firmware)} />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Firmware</span>
      </nav>
      <h1>ESP32 firmware</h1>
      <p className="lead">
        {filtered && ok
          ? filteredLead(firmware.length, catalogTotal)
          : firmwareLeadCopy(sort === "relevance" ? "popularity" : sort, firmware.length)}
      </p>
      {(ok || facets) && <FirmwareFilters key={apiQueryString(query)} query={query} facets={facets} results={ok ? firmware.length : null} />}
      {firmware.length > 0 && (
        <>
          <p className="firmware-metric-note">★ Stars · ⑂ Forks. Counts cover the linked GitHub repository, including shared repositories. Recipe evidence determines board compatibility.</p>
          <FirmwareBrowseList key={apiQueryString(query)} firmware={firmware} />
        </>
      )}
      {ok && firmware.length === 0 && filtered && (
        <p className="firmware-empty" role="status">
          {emptyCopy(query)} <Link href="/firmware">Show all firmware</Link>
        </p>
      )}
    </main>
  );
}
