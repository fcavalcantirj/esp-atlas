"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import PartDetailView from "@/components/part/PartDetailView";
import PartViewTracker from "@/components/part/PartViewTracker";
import TrackedLink from "@/components/TrackedLink";
import { ApiError, getPart, type PartDetail } from "@/lib/api";
import { track } from "@/lib/analytics";
import { contributingUrl } from "@/lib/github";

type State =
  | { status: "loading" }
  | { status: "ok"; part: PartDetail }
  | { status: "not_found" }
  | { status: "error"; message: string };

// Fallback when the server could not reach the API in time (cold function,
// preview deployment protection, ...): fetch from the browser instead.
export default function PartDetailClient({ id }: { id: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getPart(id)
      .then((part) => {
        if (!cancelled) setState({ status: "ok", part });
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
      <PartDetailView part={state.part} />
    </>
  );
}
