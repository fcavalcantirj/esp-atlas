import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import PartDetailClient from "@/components/part/PartDetailClient";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import { fetchPartDetail } from "@/lib/api-server";
import { firstSentence, typeLabel } from "@/lib/format";
import { SITE_NAME } from "@/lib/site";
import { partGraph } from "@/lib/structured-data";

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
  const title = `${part.name} (${part.vendor_or_brand}) — ${typeLabel(part.type)} specs`;
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

  return (
    <main id="main" className="container" tabIndex={-1}>
      {result.status === "ok" ? (
        <>
          <JsonLd data={partGraph(result.data)} />
          <PartViewTracker part={result.data} />
          <PartDetailView part={result.data} />
        </>
      ) : (
        <PartDetailClient id={id} />
      )}
    </main>
  );
}
