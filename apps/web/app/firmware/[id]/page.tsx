import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import FirmwareReadme from "@/components/firmware/FirmwareReadme";
import FirmwareDetailView from "@/components/firmware/FirmwareDetailView";
import type { Firmware } from "@/lib/api";
import { dataOrThrow, fetchAllPartsResult, fetchFirmware, fetchRecipesForFirmware } from "@/lib/api-server";
import { detailRobots } from "@/lib/detail-robots";
import { firmwareMetaDescription, firmwareMetaTitle } from "@/lib/format";
import { fetchReadme, type RepoReadme } from "@/lib/readme";
import { SITE_NAME } from "@/lib/site";

// Render each detail page on its first visit, then serve it from the cache (ISR) instead of rendering
// every request (2026-11-18: these routes were dynamic, `cache-control: private, no-store`, x-vercel-cache
// MISS on every hit). No path is pre-rendered at build (an empty list): the catalog API is not reachable
// during a Vercel build, and a cold first render is the same as today's every render. The data fetches keep
// their own revalidate and `catalog`/`popularity` tags, so POST /api/revalidate still purges these pages.
export function generateStaticParams() {
  return [];
}

// Firmware hub: the project's own identity (GET /firmware/<id>) plus the
// reverse view — every board a recipe targets it for, grouped by trust tier,
// same shape as the board page's "Firmware for this board" section but from
// the other side of the edge.

async function DeferredReadme({ firmware, readmePromise }: { firmware: Firmware; readmePromise: Promise<RepoReadme | null> }) {
  return <FirmwareReadme firmware={firmware} readme={await readmePromise} />;
}

export async function generateMetadata({ params }: PageProps<"/firmware/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await fetchFirmware(id);
  if (result.status === "error") throw new Error(`Firmware API unavailable for ${id}`);
  if (result.status !== "ok") {
    return { title: id, robots: detailRobots(result.status) };
  }
  const firmware = result.data;
  const title = firmwareMetaTitle(firmware);
  const description = firmwareMetaDescription(firmware);
  const path = `/firmware/${encodeURIComponent(id)}`;
  // Nested metadata objects replace the root ones wholesale, so siteName and
  // url must be restated here. The preview image is the segment's own
  // opengraph-image.tsx (per-firmware card), which Next adds to both og and twitter.
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "article", siteName: SITE_NAME, title, description, url: path },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function FirmwarePage({ params }: PageProps<"/firmware/[id]">) {
  const { id } = await params;
  const result = await fetchFirmware(id);
  if (result.status === "not_found") notFound();
  if (result.status === "error") throw new Error(`Firmware API unavailable for ${id}`);

  const firmware = result.data;
  // The upstream README is optional. Start its bounded fetch now, but stream
  // the firmware identity and cited board recipes as soon as their APIs answer.
  const readmePromise = fetchReadme(firmware.url);
  const [recipesResult, partsResult] = await Promise.all([
    fetchRecipesForFirmware(id),
    fetchAllPartsResult(),
  ]);
  // A failed fetch throws rather than render no boards: the ISR cache would keep that page (dataOrThrow).
  const recipes = dataOrThrow(recipesResult, `Recipes API for ${id}`).results;
  const parts = dataOrThrow(partsResult, "Parts API").results;
  return (
    <FirmwareDetailView
      firmware={firmware}
      recipes={recipes}
      parts={parts}
      readmeSection={
        <Suspense fallback={null}>
          <DeferredReadme firmware={firmware} readmePromise={readmePromise} />
        </Suspense>
      }
    />
  );
}
