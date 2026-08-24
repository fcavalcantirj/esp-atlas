import type { Metadata } from "next";
import PartTypeIndex, { TYPE_INDEX_COPY } from "@/components/PartTypeIndex";
import { fetchAllParts } from "@/lib/api-server";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

// /socs: the typed index behind the "SoCs" breadcrumb on every soc page. Incremental
// static like /brands: regenerated every five minutes, never thrown on a cold API.
export const revalidate = 300;

export async function generateMetadata(): Promise<Metadata> {
  const parts = await fetchAllParts();
  const { title, description } = TYPE_INDEX_COPY.soc;
  return {
    title,
    description,
    alternates: { canonical: "/socs" },
    // A cold API must not get an empty index cached by a crawler.
    robots: parts.some((p) => p.type === "soc") ? undefined : { index: false, follow: true },
    openGraph: { type: "website", siteName: SITE_NAME, title: `${title} · ${SITE_NAME}`, description, url: "/socs", images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title: `${title} · ${SITE_NAME}`, description, images: [OG_IMAGE.url] },
  };
}

export default function Page() {
  return <PartTypeIndex type="soc" />;
}
