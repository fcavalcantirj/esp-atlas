import type { Metadata } from "next";
import PartTypeIndex, { TYPE_INDEX_COPY } from "@/components/PartTypeIndex";
import { fetchAllParts } from "@/lib/api-server";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

// /boards: the typed index behind the "Boards" breadcrumb on every board page. Incremental
// static like /brands: regenerated every five minutes, never thrown on a cold API.
export const revalidate = 300;

export async function generateMetadata(): Promise<Metadata> {
  const parts = await fetchAllParts();
  const { title, description } = TYPE_INDEX_COPY.board;
  return {
    title,
    description,
    alternates: { canonical: "/boards" },
    // A cold API must not get an empty index cached by a crawler.
    robots: parts.some((p) => p.type === "board") ? undefined : { index: false, follow: true },
    openGraph: { type: "website", siteName: SITE_NAME, title: `${title} · ${SITE_NAME}`, description, url: "/boards", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${title} · ${SITE_NAME}`, description, images: [OG_IMAGE.url] },
  };
}

export default function Page() {
  return <PartTypeIndex type="board" />;
}
