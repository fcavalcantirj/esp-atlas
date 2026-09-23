import type { Metadata } from "next";
import { notFound } from "next/navigation";
import FirmwareDetailClient from "@/components/firmware/FirmwareDetailClient";
import FirmwareDetailView from "@/components/firmware/FirmwareDetailView";
import { fetchAllParts, fetchFirmware, fetchRecipesForFirmware } from "@/lib/api-server";
import { detailRobots } from "@/lib/detail-robots";
import { firmwareMetaDescription } from "@/lib/format";
import { fetchReadme } from "@/lib/readme";
import { SITE_NAME } from "@/lib/site";

// Firmware hub: the project's own identity (GET /firmware/<id>) plus the
// reverse view — every board a recipe targets it for, grouped by trust tier,
// same shape as the board page's "Firmware for this board" section but from
// the other side of the edge.


export async function generateMetadata({ params }: PageProps<"/firmware/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await fetchFirmware(id);
  if (result.status !== "ok") {
    return { title: id, robots: detailRobots(result.status) };
  }
  const firmware = result.data;
  const title = `${firmware.name} — ESP32 firmware`;
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
  // Cold or gated API: render client-side instead of a dead end.
  if (result.status !== "ok") return <FirmwareDetailClient id={id} />;

  const firmware = result.data;
  const [recipesResult, parts, readme] = await Promise.all([
    fetchRecipesForFirmware(id),
    fetchAllParts(),
    firmware.readme_en ? Promise.resolve(null) : fetchReadme(firmware.url),
  ]);
  const recipes = recipesResult.status === "ok" ? recipesResult.data.results : [];
  return <FirmwareDetailView firmware={firmware} recipes={recipes} parts={parts} readme={readme} />;
}
