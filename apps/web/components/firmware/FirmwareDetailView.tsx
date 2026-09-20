import Link from "next/link";
import type { ReactNode } from "react";
import Markdown from "react-markdown";
import JsonLd from "@/components/JsonLd";
import RecipeGroupList from "@/components/RecipeGroupList";
import TrackedLink from "@/components/TrackedLink";
import type { Firmware, PartRecord, Recipe } from "@/lib/api";
import { firmwareCategoryLabel } from "@/lib/format";
import type { RepoReadme } from "@/lib/readme";
import { firmwareBoardRows } from "@/lib/recipe-rows";
import { firmwareGraph } from "@/lib/structured-data";

// Presentational firmware hub: the project's identity plus the reverse view —
// every board a recipe targets it for, grouped by trust tier, each with its
// flash action. Used by the server-rendered page and the client fallback.

// Spike placeholder (frontend-only, reversible): a tick-time job will have Groq
// summarize + ground each firmware's README and cache the result on the record
// as `firmware.summary`. Until that pipeline lands, this map stands in for it --
// nothing here is fabricated on the fly, and the map is deleted once
// `firmware.summary` is populated for real.
const SPIKE_DEKS: Record<string, string> = {
  "ai-stackchan2-readme":
    "A ChatGPT-powered talking desktop companion for the M5Stack Core2 - hold a spoken conversation while a servo-driven face reacts, all configured from a built-in Wi-Fi web UI.",
};

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

export default function FirmwareDetailView({
  firmware,
  recipes,
  parts,
  readme = null,
}: {
  firmware: Firmware;
  recipes: Recipe[];
  parts: PartRecord[];
  /** Resolved by the caller (server-fetched on the SSR path, client-fetched on
   * the cold-API fallback) -- this stays a plain, synchronous component so it
   * can render from both a server component and FirmwareDetailClient. */
  readme?: RepoReadme | null;
}) {
  const rows = firmwareBoardRows(recipes, parts, firmware);
  const boardById = new Map(parts.map((p) => [p.id, p]));
  const boards = recipes.map((r) => boardById.get(r.board)).filter((b): b is PartRecord => b !== undefined);
  const dek = (firmware as { summary?: string }).summary ?? SPIKE_DEKS[firmware.id];

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
      {dek && (
        <>
          <p className="firmware-dek">{dek}</p>
          <p className="firmware-dek-marker muted">auto-summary</p>
        </>
      )}
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
      {readme && (
        <section className="firmware-readme" aria-labelledby="firmware-readme">
          <p className="firmware-readme-label" id="firmware-readme">
            README
          </p>
          <div className="firmware-readme-collapse">
            <div className="firmware-readme-body">
              <Markdown>{readme.markdown}</Markdown>
            </div>
          </div>
          <p>
            <TrackedLink href={firmware.url} linkType="source" extra={{ firmware_id: firmware.id, from: "readme" }}>
              Read the full README on GitHub
            </TrackedLink>
          </p>
          <p className="firmware-readme-caption muted">
            source github.com/{readme.owner}/{readme.repo}
          </p>
        </section>
      )}
    </main>
  );
}
