import type { Metadata } from "next";
import Link from "next/link";
import FirmwareBrowseList from "@/components/FirmwareBrowseList";
import FirmwareSortControl from "@/components/FirmwareSortControl";
import JsonLd from "@/components/JsonLd";
import { fetchFirmwareList } from "@/lib/api-server";
import { firmwareLeadCopy, firmwareRobots, resolveSort } from "@/lib/firmware-sort";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { firmwareIndexGraph } from "@/lib/structured-data";

// Index of every firmware in the dataset, from GET /firmware. Incremental
// static like /brands: regenerated every five minutes, so a cold build-time
// render (API not running -> empty list, noindex) clears within minutes of
// the first request. The fetch never throws.
export const revalidate = 300;

const TITLE = "ESP32 firmware — what runs on what";
const DESCRIPTION =
  "Every flashable ESP32 firmware project in the esp-atlas dataset — Marauder, NEMO, Launcher and more — cited to its own repo, with the boards it's verified to run on.";

export async function generateMetadata({ searchParams }: PageProps<"/firmware">): Promise<Metadata> {
  const { sort: rawSort } = await searchParams;
  const sort = resolveSort(rawSort);
  const result = await fetchFirmwareList(sort);
  return {
    title: TITLE,
    description: DESCRIPTION,
    // SPEC-firmware-ordering.md §3: every sort order canonicalizes to the
    // bare index so the 5 orders never become indexable near-duplicates.
    alternates: { canonical: "/firmware" },
    robots: firmwareRobots(sort, result.status === "ok"),
    openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/firmware", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
  };
}

export default async function FirmwareIndexPage({ searchParams }: PageProps<"/firmware">) {
  const { sort: rawSort } = await searchParams;
  const sort = resolveSort(rawSort);
  const result = await fetchFirmwareList(sort);
  // Already ordered server-side by the API -- see SPEC-firmware-ordering.md §1
  // (Golden Rule 3: the API sorts, this page only renders what it returns).
  const firmware = result.status === "ok" ? result.data.results : [];

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      {firmware.length > 0 && <JsonLd data={firmwareIndexGraph(firmware)} />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Firmware</span>
      </nav>
      <h1>ESP32 firmware</h1>
      <p className="lead">{firmwareLeadCopy(sort, firmware.length)}</p>
      {firmware.length > 0 && (
        <>
          <FirmwareSortControl sort={sort} />
          <FirmwareBrowseList firmware={firmware} />
        </>
      )}
    </main>
  );
}
