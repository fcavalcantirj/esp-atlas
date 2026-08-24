import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import JsonLd from "@/components/JsonLd";
import RecipeGroupList, { type RecipeRow } from "@/components/RecipeGroupList";
import TrackedLink from "@/components/TrackedLink";
import { fetchAllParts, fetchFirmware, fetchRecipesForFirmware } from "@/lib/api-server";
import { handoffFor } from "@/lib/esp-web-tools";
import type { PartRecord } from "@/lib/api";
import { brandLabel } from "@/lib/brand";
import { firmwareCategoryLabel } from "@/lib/format";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { firmwareGraph } from "@/lib/structured-data";

// Firmware hub: the project's own identity (GET /firmware/<id>) plus the
// reverse view — every board a recipe targets it for, grouped by trust tier,
// same shape as the board page's "Firmware for this board" section but from
// the other side of the edge.

function Chips({ values, on }: { values: string[]; on?: boolean }) {
  if (values.length === 0) return null;
  return (
    <span className="spec-chips">
      {values.map((v) => (
        <span key={v} className={`spec-chip${on ? " spec-chip--on" : ""}`}>
          {v}
        </span>
      ))}
    </span>
  );
}

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

  if (result.status !== "ok") {
    return (
      <main id="main" className="container container--narrow" tabIndex={-1}>
        <h1>{id}</h1>
        <p className="lead">The API did not answer in time — this firmware page could not be rendered. Try again in a moment.</p>
      </main>
    );
  }

  const firmware = result.data;
  const [recipesResult, allParts] = await Promise.all([fetchRecipesForFirmware(id), fetchAllParts()]);
  const recipes = recipesResult.status === "ok" ? recipesResult.data.results : [];
  const boardById = new Map(allParts.map((p) => [p.id, p]));

  const handoff = handoffFor(firmware);
  const rows: RecipeRow[] = recipes.map((recipe) => {
    const board = boardById.get(recipe.board);
    return {
      recipe,
      href: `/parts/${encodeURIComponent(recipe.board)}`,
      name: board?.name || recipe.board,
      meta: board ? brandLabel(board) : null,
      handoff,
    };
  });

  const boards = recipes.map((r) => boardById.get(r.board)).filter((b): b is PartRecord => b !== undefined);

  const details: { label: string; value: ReactNode }[] = [];
  if (firmware.maintainer) details.push({ label: "Maintainer", value: firmware.maintainer });
  if (firmware.license) details.push({ label: "License", value: firmware.license });
  if (firmware.distribution.length > 0) details.push({ label: "Distribution", value: <Chips values={firmware.distribution} /> });
  if (firmware.capabilities.length > 0) details.push({ label: "Capabilities", value: <Chips values={firmware.capabilities} on /> });
  if (firmware.socs.length > 0) details.push({ label: "Chip families", value: <Chips values={firmware.socs} /> });

  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <JsonLd data={firmwareGraph(firmware, boards)} />
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <Link href="/firmware">Firmware</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">{firmware.name}</span>
      </nav>
      <h1>{firmware.name}</h1>
      <p className="lead">
        <span className="badge">{firmwareCategoryLabel(firmware.category)}</span>{" "}
        <TrackedLink href={firmware.url} linkType="source" extra={{ firmware_id: firmware.id }}>
          View the repo
        </TrackedLink>
      </p>
      {details.length > 0 && (
        <section aria-label="Details">
          <dl className="spec-dl">
            {details.map((d) => (
              <div key={d.label} style={{ display: "contents" }}>
                <dt>{d.label}</dt>
                <dd>{d.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      <section className="firmware-boards" aria-labelledby="firmware-boards">
        <h2 id="firmware-boards">Runs on these boards</h2>
        {rows.length === 0 ? <p className="muted">No boards recorded for this firmware yet.</p> : <RecipeGroupList rows={rows} />}
      </section>
    </main>
  );
}
