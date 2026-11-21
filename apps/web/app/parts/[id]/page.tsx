import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import type { RecipeRow } from "@/components/RecipeGroupList";
import type { Firmware } from "@/lib/api";
import { dataOrThrow, fetchFirmwareList, fetchPartDetail, fetchRecipesForBoard } from "@/lib/api-server";
import { firmwareForChip } from "@/lib/chip-firmware";
import { detailRobots } from "@/lib/detail-robots";
import { partMetaDescription, partMetaTitle } from "@/lib/format";
import { asString, fmObject } from "@/lib/frontmatter";
import { boardFirmwareRows } from "@/lib/recipe-rows";
import { SITE_NAME } from "@/lib/site";
import { partGraph } from "@/lib/structured-data";
import type { DownloadMode } from "@/lib/troubleshooter";

// Render each detail page on its first visit, then serve it from the cache (ISR) instead of rendering
// every request (2026-11-18: these routes were dynamic, `cache-control: private, no-store`, x-vercel-cache
// MISS on every hit). No path is pre-rendered at build (an empty list): the catalog API is not reachable
// during a Vercel build, and a cold first render is the same as today's every render. The data fetches keep
// their own revalidate and `catalog`/`popularity` tags, so POST /api/revalidate still purges these pages.
export function generateStaticParams() {
  return [];
}

// Two API responses joined for display (lib/recipe-rows.ts). A failed fetch
// throws rather than render the page without its firmware rows: the ISR cache
// would keep that page until the next revalidation (dataOrThrow).
async function fetchBoardFirmwareRows(
  boardId: string,
  boardName: string,
  usbConnector: string | null,
  downloadMode: DownloadMode | null,
): Promise<RecipeRow[]> {
  const [recipesResult, firmwareResult] = await Promise.all([fetchRecipesForBoard(boardId), fetchFirmwareList()]);
  const recipes = dataOrThrow(recipesResult, `Recipes API for ${boardId}`).results;
  const firmware = dataOrThrow(firmwareResult, "Firmware API").results;
  return boardFirmwareRows(recipes, firmware, boardName, usbConnector, downloadMode);
}

// The chip hub's firmware (SPEC-serp-ctr.md §4); a chip with no firmware
// yields no rows, so the section simply doesn't render. A failed fetch throws (see above).
async function fetchChipFirmware(socId: string): Promise<Firmware[]> {
  return firmwareForChip(dataOrThrow(await fetchFirmwareList(), "Firmware API").results, socId);
}

// The board's cited download_mode frontmatter (mode/steps/note), for the flash
// panel's per-board download-mode hint. Absent on many records (cite-or-omit).
function downloadModeFromFrontmatter(fm: Record<string, unknown>): DownloadMode | null {
  const dm = fmObject(fm, "download_mode");
  if (!dm) return null;
  const mode = asString(dm.mode);
  if (!mode) return null;
  return { mode, steps: asString(dm.steps), note: asString(dm.note) };
}

// Server-rendered so every part page ships with its own title/description for
// search engines and link previews. The API fetch is cached for an hour; if the
// Python function is cold or unreachable, the page must fail with a server
// error rather than publish a 200/noindex loading shell for a valid record.

export async function generateMetadata({ params }: PageProps<"/parts/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await fetchPartDetail(id);
  if (result.status === "error") throw new Error(`Part API unavailable for ${id}`);
  if (result.status !== "ok") {
    return { title: id, robots: detailRobots(result.status) };
  }
  const part = result.data;
  const hasPinout = Boolean(asString(fmObject(part.frontmatter, "images")?.pinout));
  const seoTitle = asString(part.frontmatter.seo_title);
  const title = partMetaTitle({ ...part, seo_title: seoTitle }, hasPinout, part.related.length > 0);
  const description = partMetaDescription(part, part.body);
  const path = `/parts/${encodeURIComponent(part.id)}`;
  // Nested metadata objects replace the root ones wholesale, so siteName and
  // url must be restated here. The preview image is the segment's own
  // opengraph-image.tsx (per-part card), which Next adds to both og and twitter.
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "article", siteName: SITE_NAME, title, description, url: path },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function PartPage({ params }: PageProps<"/parts/[id]">) {
  const { id } = await params;
  const result = await fetchPartDetail(id);
  if (result.status === "not_found") notFound();
  if (result.status === "error") throw new Error(`Part API unavailable for ${id}`);

  // The board's cited USB connector feeds the flash panel's plug-in hint; absent on many records (cite-or-omit).
  const usbConnector = asString(fmObject(result.data.frontmatter, "usb")?.connector);
  const downloadMode = downloadModeFromFrontmatter(result.data.frontmatter);
  const boardFirmwareRows = result.data.type === "board"
    ? await fetchBoardFirmwareRows(id, result.data.name, usbConnector, downloadMode)
    : null;
  const chipFirmware = result.data.type === "soc" ? await fetchChipFirmware(id) : [];

  return (
    <main id="main" className="container" tabIndex={-1}>
      <JsonLd data={partGraph(result.data)} />
      <PartViewTracker part={result.data} />
      <PartDetailView part={result.data} boardFirmwareRows={boardFirmwareRows} chipFirmware={chipFirmware} />
    </main>
  );
}
