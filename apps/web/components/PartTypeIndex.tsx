import Link from "next/link";
import BrowseSection, { type BrowseItem } from "@/components/BrowseSection";
import JsonLd from "@/components/JsonLd";
import type { PartRecord } from "@/lib/api";
import { fetchAllParts } from "@/lib/api-server";
import { brandLabel } from "@/lib/brand";
import { typePlural } from "@/lib/format";
import { typeIndexPath } from "@/lib/routes";
import { partTypeIndexGraph } from "@/lib/structured-data";

export type IndexedType = "board" | "module" | "soc";

export const TYPE_INDEX_COPY: Record<IndexedType, { title: string; description: string; hint: string }> = {
  board: {
    title: "ESP32 dev boards",
    description:
      "Every ESP32 development board in the esp-atlas dataset — by Espressif, Adafruit, M5Stack, LILYGO, Seeed and more — each spec cited to an official datasheet or vendor page.",
    hint: "Every board in the atlas, A–Z, with its brand and chip.",
  },
  module: {
    title: "ESP32 modules",
    description:
      "Every ESP32 module in the esp-atlas dataset — WROOM, WROVER, MINI and friends — with the SoC each one wraps, cited to Espressif's datasheets.",
    hint: "Every module in the atlas, A–Z, with the chip inside it.",
  },
  soc: {
    title: "ESP32 SoCs",
    description:
      "Every ESP32 system-on-chip in the esp-atlas dataset — classic ESP32, S2, S3, C3, C6, H2, P4 and more — with radios, USB and the boards built on each.",
    hint: "Every chip in the atlas, A–Z, with how many parts are built on it.",
  },
};

function note(part: PartRecord, all: PartRecord[]): string {
  if (part.type === "soc") {
    const n = all.filter((p) => p.type !== "soc" && p.soc_ref === part.id).length;
    return `${n} ${n === 1 ? "part" : "parts"} on this chip`;
  }
  const chip = part.soc_ref ?? part.module_ref;
  return chip ? `${brandLabel(part)} · ${chip}` : brandLabel(part);
}

// The typed index behind a part page's middle breadcrumb (Home › Boards › X):
// a crawlable A–Z list of one part type, same shape as /brands. Rendered from
// GET /parts, incremental-static like the other indexes; a cold API gives an
// honest empty state rather than an error.
export default async function PartTypeIndex({ type }: { type: IndexedType }) {
  const all = await fetchAllParts();
  const parts = all.filter((p) => p.type === type).sort((a, b) => a.name.localeCompare(b.name));
  const copy = TYPE_INDEX_COPY[type];
  const path = typeIndexPath(type) ?? "/";
  const items: BrowseItem[] = parts.map((part) => ({
    href: `/parts/${encodeURIComponent(part.id)}`,
    name: part.name,
    note: note(part, all),
    partId: part.id,
    partType: part.type,
  }));

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      {parts.length > 0 && <JsonLd data={partTypeIndexGraph(type, copy.title, path, parts)} />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">{typePlural(type)}</span>
      </nav>
      <h1>{typePlural(type)}</h1>
      <p className="lead">
        {parts.length > 0
          ? `${parts.length} ${typePlural(type).toLowerCase()} in the atlas — every spec cited to an official source.`
          : `The ${typePlural(type).toLowerCase()} list could not be loaded right now — try again in a moment.`}
      </p>
      <BrowseSection id={`${type}s`} title={`All ${typePlural(type).toLowerCase()}`} hint={copy.hint} items={items} origin="browse" />
    </main>
  );
}
