import type { Metadata } from "next";
import Link from "next/link";
import FirmwareCard from "@/components/FirmwareCard";
import JsonLd from "@/components/JsonLd";
import { fetchFirmwareList } from "@/lib/api-server";
import { firmwareCategoryLabel } from "@/lib/format";
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

// SPEC-wizard.md's fixed category list, in that order; any other category the
// data carries is appended after, alphabetically.
const CATEGORY_ORDER = ["pentest", "mesh", "badusb", "display", "home", "multi"];

function categoryRank(category: string): number {
  const i = CATEGORY_ORDER.indexOf(category);
  return i === -1 ? CATEGORY_ORDER.length : i;
}

export async function generateMetadata(): Promise<Metadata> {
  const result = await fetchFirmwareList();
  return {
    title: TITLE,
    description: DESCRIPTION,
    alternates: { canonical: "/firmware" },
    // A cold API must not get an empty index cached by a crawler.
    robots: result.status === "ok" ? undefined : { index: false, follow: true },
    openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/firmware", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
  };
}

export default async function FirmwareIndexPage() {
  const result = await fetchFirmwareList();
  const firmware = result.status === "ok" ? result.data.results : [];
  const categories = [...new Set(firmware.map((fw) => fw.category))].sort(
    (a, b) => categoryRank(a) - categoryRank(b) || a.localeCompare(b),
  );
  const groups = categories.map((category) => ({ category, items: firmware.filter((fw) => fw.category === category) }));

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      {firmware.length > 0 && <JsonLd data={firmwareIndexGraph(firmware)} />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Firmware</span>
      </nav>
      <h1>Firmware</h1>
      <p className="lead">
        {firmware.length > 0
          ? `${firmware.length} flashable firmware projects — open one to see the boards it's verified to run on.`
          : "The firmware list could not be loaded right now — try again in a moment."}
      </p>
      {groups.map((group) => (
        <section key={group.category} className="brand-group" aria-labelledby={`firmware-${group.category}`}>
          <h2 id={`firmware-${group.category}`}>
            {firmwareCategoryLabel(group.category)} ({group.items.length})
          </h2>
          <ul className="results-list">
            {group.items.map((fw) => (
              <FirmwareCard key={fw.id} firmware={fw} />
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
