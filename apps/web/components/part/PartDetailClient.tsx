"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import type { RecipeRow } from "@/components/RecipeGroupList";
import TrackedLink from "@/components/TrackedLink";
import { ApiError, getPart, getRecipesForBoard, listFirmware, type PartDetail } from "@/lib/api";
import { track } from "@/lib/analytics";
import { asString, fmObject } from "@/lib/frontmatter";
import { contributingUrl } from "@/lib/github";
import { boardFirmwareRows } from "@/lib/recipe-rows";

type State =
  | { status: "loading" }
  | { status: "ok"; part: PartDetail; rows: RecipeRow[] | null }
  | { status: "not_found" }
  | { status: "error"; message: string };

// Fallback when the server could not reach the API in time (cold function,
// preview deployment protection, ...): fetch from the browser instead. Boards
// also load their recipes here, so the Flash Wizard's action renders on this
// path too instead of silently disappearing with the firmware section.
async function loadBoardRows(part: PartDetail): Promise<RecipeRow[] | null> {
  if (part.type !== "board") return null;
  const [recipes, firmware] = await Promise.all([
    getRecipesForBoard(part.id).then((r) => r.results, () => null),
    listFirmware().then((r) => r.results, () => []),
  ]);
  if (recipes === null) return [];
  return boardFirmwareRows(recipes, firmware, asString(fmObject(part.frontmatter, "usb")?.connector));
}

export default function PartDetailClient({ id }: { id: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getPart(id)
      .then(async (part) => {
        const rows = await loadBoardRows(part);
        if (!cancelled) setState({ status: "ok", part, rows });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          track("not_found", { path: `/parts/${id}` });
          setState({ status: "not_found" });
          return;
        }
        track("api_error", { endpoint: "/parts/{id}", status: err instanceof ApiError ? err.status : "network" });
        setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (state.status === "loading") {
    return (
      <div aria-busy="true" aria-live="polite">
        <div className="detail-skeleton" style={{ width: "40%", height: "2rem" }} />
        <div className="detail-skeleton" style={{ width: "60%" }} />
        <div className="detail-skeleton" style={{ width: "80%" }} />
        <p className="muted">Loading {id}…</p>
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <div className="empty-state">
        <h2>Not in esp-atlas yet</h2>
        <p>
          There is no part with the id <code>{id}</code>. If it exists, it&apos;s a one-file PR away.
        </p>
        <p>
          <Link href="/" className="btn btn--primary">
            Back to the wizard
          </Link>{" "}
          <TrackedLink href={contributingUrl()} linkType="contributing" className="btn">
            Add a part
          </TrackedLink>
        </p>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="empty-state">
        <h2>The API did not answer</h2>
        <p className="error mono">{state.message}</p>
        <p>
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            Try again
          </button>
        </p>
      </div>
    );
  }

  return (
    <>
      <PartViewTracker part={state.part} />
      <PartDetailView part={state.part} boardFirmwareRows={state.rows} />
    </>
  );
}
