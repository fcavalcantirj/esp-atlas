import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PartDetailClient from "@/components/part/PartDetailClient";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import type { RecipeRow } from "@/components/RecipeGroupList";
import { fetchFirmwareList, fetchPartDetail, fetchRecipesForBoard } from "@/lib/api-server";
import { brandLabel } from "@/lib/brand";
import { firstSentence, typeLabel } from "@/lib/format";
import { asString, fmObject } from "@/lib/frontmatter";
import { boardFirmwareRows } from "@/lib/recipe-rows";
import { SITE_NAME } from "@/lib/site";
import { partGraph } from "@/lib/structured-data";

// Two API responses joined for display (lib/recipe-rows.ts); a failed recipes
// fetch yields no rows rather than an error.
async function fetchBoardFirmwareRows(boardId: string, usbConnector: string | null): Promise<RecipeRow[]> {
  const [recipesResult, firmwareResult] = await Promise.all([fetchRecipesForBoard(boardId), fetchFirmwareList()]);
  if (recipesResult.status !== "ok") return [];
  const firmware = firmwareResult.status === "ok" ? firmwareResult.data.results : [];
  return boardFirmwareRows(recipesResult.data.results, firmware, usbConnector);
}

// Server-rendered so every part page ships with its own title/description for
// search engines and link previews. The API fetch is cached for an hour; if the
// Python function is cold or unreachable, the page falls back to client-side
// fetching instead of failing.

export async function generateMetadata({ params }: PageProps<"/parts/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await fetchPartDetail(id);
  if (result.status !== "ok") {
    return { title: id, robots: result.status === "not_found" ? { index: false } : undefined };
  }
  const part = result.data;
  const title = `${part.name} (${brandLabel(part)}) — ${typeLabel(part.type)} specs`;
  const description =
    firstSentence(part.body) || `${part.name}: datasheet-verified ESP32 ${part.type} specs on ${SITE_NAME}.`;
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

  // The board's cited USB connector feeds the flash panel's plug-in hint; absent on many records (cite-or-omit).
  const usbConnector = result.status === "ok" ? asString(fmObject(result.data.frontmatter, "usb")?.connector) : null;
  const boardFirmwareRows =
    result.status === "ok" && result.data.type === "board" ? await fetchBoardFirmwareRows(id, usbConnector) : null;

  return (
    <main id="main" className="container" tabIndex={-1}>
      {result.status === "ok" ? (
        <>
          <JsonLd data={partGraph(result.data)} />
          <PartViewTracker part={result.data} />
          <PartDetailView part={result.data} boardFirmwareRows={boardFirmwareRows} />
        </>
      ) : (
        <PartDetailClient id={id} />
      )}
    </main>
  );
}
