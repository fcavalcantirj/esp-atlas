import type { Metadata } from "next";
import { notFound } from "next/navigation";
import PartDetailClient from "@/components/part/PartDetailClient";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import { fetchPartDetail } from "@/lib/api-server";
import { firstSentence, typeLabel } from "@/lib/format";
import { SITE_NAME } from "@/lib/site";

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
  return {
    title,
    description,
    alternates: { canonical: `/parts/${encodeURIComponent(part.id)}` },
    openGraph: { title, description, type: "article" },
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
          <PartViewTracker part={result.data} />
          <PartDetailView part={result.data} />
        </>
      ) : (
        <PartDetailClient id={id} />
      )}
    </main>
  );
}
