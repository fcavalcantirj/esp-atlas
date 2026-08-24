import type { Metadata } from "next";
import { notFound } from "next/navigation";
import FirmwareDetailClient from "@/components/firmware/FirmwareDetailClient";
import FirmwareDetailView from "@/components/firmware/FirmwareDetailView";
import { fetchAllParts, fetchFirmware, fetchRecipesForFirmware } from "@/lib/api-server";
import { firmwareCategoryLabel } from "@/lib/format";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

// Firmware hub: the project's own identity (GET /firmware/<id>) plus the
// reverse view — every board a recipe targets it for, grouped by trust tier,
// same shape as the board page's "Firmware for this board" section but from
// the other side of the edge.


export async function generateMetadata({ params }: PageProps<"/firmware/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await fetchFirmware(id);
  if (result.status !== "ok") {
    return { title: id, robots: result.status === "not_found" ? { index: false } : undefined };
  }
  const firmware = result.data;
  const title = `${firmware.name} — ESP32 firmware`;
  const description = `${firmware.name}: ${firmwareCategoryLabel(firmware.category)} firmware${
    firmware.maintainer ? ` maintained by ${firmware.maintainer}` : ""
  } for ${firmware.socs.join(", ") || "ESP32"} — see the boards it's verified to run on.`;
  const path = `/firmware/${encodeURIComponent(id)}`;
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: "website", siteName: SITE_NAME, title, description, url: path, images: [OG_IMAGE] },
    twitter: { card: "summary_large_image", title, description, images: [OG_IMAGE.url] },
  };
}

export default async function FirmwarePage({ params }: PageProps<"/firmware/[id]">) {
  const { id } = await params;
  const result = await fetchFirmware(id);
  if (result.status === "not_found") notFound();
  // Cold or gated API: render client-side instead of a dead end.
  if (result.status !== "ok") return <FirmwareDetailClient id={id} />;

  const firmware = result.data;
  const [recipesResult, parts] = await Promise.all([fetchRecipesForFirmware(id), fetchAllParts()]);
  const recipes = recipesResult.status === "ok" ? recipesResult.data.results : [];
  return <FirmwareDetailView firmware={firmware} recipes={recipes} parts={parts} />;
}
