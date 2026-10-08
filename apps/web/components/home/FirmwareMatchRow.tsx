"use client";

import Link from "next/link";
import { useState } from "react";
import PopularityGlance from "@/components/PopularityGlance";
import RecipeGroupList, { type RecipeRow } from "@/components/RecipeGroupList";
import type { Firmware, PartRecord } from "@/lib/api";
import { getRecipesForFirmware } from "@/lib/api";
import { track, type ResultOrigin } from "@/lib/analytics";
import type { Compat } from "@/lib/board-compat";
import { boardsLabel, firmwareCategoryLabel } from "@/lib/format";
import { firmwareBoardRows } from "@/lib/recipe-rows";

// One matched firmware (detect hero / intent search), expandable into its
// real per-board flash actions -- never a fabricated "flash now" on a
// firmware this page hasn't actually loaded a recipe for. Reuses the exact
// board-page/firmware-page plumbing (lib/recipe-rows.ts, RecipeGroupList,
// FlashAction underneath it) instead of a second flash implementation.

const COMPAT_LABEL: Record<Compat, string> = {
  runs: "Runs on your chip",
  no: "Won't run on your chip",
  unknown: "Compatibility not cited",
};

type FlashState = { kind: "closed" } | { kind: "loading" } | { kind: "ready"; rows: RecipeRow[] } | { kind: "error" };

export interface FirmwareMatchRowProps {
  firmware: Firmware;
  /** The full part list, for RecipeGroupList's board names/links. */
  parts: PartRecord[];
  origin: ResultOrigin;
  position?: number;
  /** When set (a chip was detected), flash options are scoped to recipes cited for this chip family. */
  chipFamily?: string | null;
  /** The honesty badge against a detected chip -- omitted when nothing was detected. */
  compat?: Compat | null;
}

export default function FirmwareMatchRow({ firmware, parts, origin, position, chipFamily = null, compat = null }: FirmwareMatchRowProps) {
  const [flash, setFlash] = useState<FlashState>({ kind: "closed" });

  async function toggleFlash() {
    if (flash.kind === "loading") return;
    if (flash.kind !== "closed") {
      setFlash({ kind: "closed" });
      return;
    }
    setFlash({ kind: "loading" });
    track("flash_open", { recipe_id: firmware.id, method: "home_match_row" });
    try {
      const result = await getRecipesForFirmware(firmware.id);
      const recipes = chipFamily ? result.results.filter((r) => r.chip_family === chipFamily) : result.results;
      setFlash({ kind: "ready", rows: firmwareBoardRows(recipes, parts, firmware) });
    } catch {
      setFlash({ kind: "error" });
    }
  }

  const boards = boardsLabel(firmware.boards);

  return (
    <li className="match-row">
      <div className="match-row-head">
        <h3 className="match-row-title">
          <Link
            href={`/firmware/${encodeURIComponent(firmware.id)}`}
            onClick={() => track("result_click", { part_id: firmware.id, part_type: "firmware", origin, position })}
          >
            {firmware.name}
          </Link>
        </h3>
        <span className="badge">{firmwareCategoryLabel(firmware.category)}</span>
        <PopularityGlance popularity={firmware.popularity} />
        {boards && <span className="match-row-boards mono">{boards}</span>}
        {compat && <span className={`compat-badge compat-badge--${compat}`}>{COMPAT_LABEL[compat]}</span>}
      </div>
      {firmware.summary && <p className="match-row-summary muted">{firmware.summary}</p>}
      {firmware.capabilities.length > 0 && (
        <div className="spec-chips">
          {firmware.capabilities.map((capability) => (
            <span key={capability} className="spec-chip spec-chip--on">
              {capability}
            </span>
          ))}
        </div>
      )}
      <button type="button" className="btn btn--sm match-row-flash-toggle" onClick={() => void toggleFlash()}>
        {flash.kind === "closed" ? "⚡ Flash options" : flash.kind === "loading" ? "Loading…" : "Hide flash options"}
      </button>
      {flash.kind === "error" && (
        <p className="error mono">Could not load flash options right now — try again, or open the firmware page.</p>
      )}
      {flash.kind === "ready" && flash.rows.length === 0 && (
        <p className="muted">
          No recipe cited yet for this chip family — see the{" "}
          <Link href={`/firmware/${encodeURIComponent(firmware.id)}`}>full firmware page</Link> for every board it runs on.
        </p>
      )}
      {flash.kind === "ready" && flash.rows.length > 0 && <RecipeGroupList rows={flash.rows} />}
    </li>
  );
}
