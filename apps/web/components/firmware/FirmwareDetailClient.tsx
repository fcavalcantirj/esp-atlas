"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import FirmwareDetailView from "@/components/firmware/FirmwareDetailView";
import { ApiError, getFirmware, getRecipesForFirmware, listParts, type Firmware, type PartRecord, type Recipe } from "@/lib/api";
import { track } from "@/lib/analytics";

type State =
  | { status: "loading" }
  | { status: "ok"; firmware: Firmware; recipes: Recipe[]; parts: PartRecord[] }
  | { status: "not_found" }
  | { status: "error"; message: string };

// Fallback when the server could not reach the API in time (cold function,
// preview deployment protection, ...): fetch from the browser instead, recipes
// included, so the flash actions render on this path too.
export default function FirmwareDetailClient({ id }: { id: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getFirmware(id)
      .then(async (firmware) => {
        const [recipes, parts] = await Promise.all([
          getRecipesForFirmware(id).then((r) => r.results, () => []),
          listParts().then((r) => r.results, () => []),
        ]);
        if (!cancelled) setState({ status: "ok", firmware, recipes, parts });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          track("not_found", { path: `/firmware/${id}` });
          setState({ status: "not_found" });
          return;
        }
        track("api_error", { endpoint: "/firmware/{id}", status: err instanceof ApiError ? err.status : "network" });
        setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (state.status === "loading") {
    return (
      <main id="main" className="container container--wide" tabIndex={-1} aria-busy="true" aria-live="polite">
        <div className="detail-skeleton" style={{ width: "40%", height: "2rem" }} />
        <div className="detail-skeleton" style={{ width: "60%" }} />
        <p className="muted">Loading {id}…</p>
      </main>
    );
  }

  if (state.status === "not_found") {
    return (
      <main id="main" className="container container--narrow" tabIndex={-1}>
        <div className="empty-state">
          <h2>Not in esp-atlas yet</h2>
          <p>
            There is no firmware with the id <code>{id}</code>.
          </p>
          <p>
            <Link href="/firmware" className="btn btn--primary">
              All firmware
            </Link>
          </p>
        </div>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main id="main" className="container container--narrow" tabIndex={-1}>
        <div className="empty-state">
          <h2>The API did not answer</h2>
          <p className="error mono">{state.message}</p>
          <p>
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Try again
            </button>
          </p>
        </div>
      </main>
    );
  }

  return <FirmwareDetailView firmware={state.firmware} recipes={state.recipes} parts={state.parts} />;
}
