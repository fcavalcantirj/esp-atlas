"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { repositorySnapshot } from "@/lib/format";
import { popularityIdentity, popularityResponse, readLivePopularity, type LivePopularity, type PopularityRecord } from "@/lib/live-popularity";

const ENABLED = process.env.NEXT_PUBLIC_ON_VIEW_POPULARITY_ENABLED === "1";
const OUTCOME_LABEL = { fresh: "Checked this visit", cached: "Cached check", stale: "Last successful check" };

export default function FirmwarePopularity({ firmware }: { firmware: PopularityRecord }) {
  const candidate = popularityIdentity(firmware);
  const { firmwareId, sourceUrl, repoId, catalogTime } = candidate ?? {};
  const key = candidate ? JSON.stringify([firmwareId, sourceUrl, repoId, catalogTime]) : "";
  const [result, setResult] = useState<{ key: string; value: LivePopularity } | null>(null);

  useEffect(() => {
    if (!ENABLED || !firmwareId || !sourceUrl || !repoId || catalogTime === undefined) return;
    const identity = { firmwareId, sourceUrl, repoId, catalogTime };
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10_000);
    // Defer one task so a discarded StrictMode effect cannot spend a request.
    const start = setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/firmware/${encodeURIComponent(identity.firmwareId)}/popularity/live`, {
          signal: controller.signal, cache: "no-store", redirect: "error", headers: { Accept: "application/json" },
        });
        const value = readLivePopularity(await popularityResponse(response), identity);
        if (!controller.signal.aborted && value) setResult({ key, value });
      } catch {
        // This optional enhancement never hides or replaces the catalog on failure.
      } finally { clearTimeout(timeout); }
    }, 0);
    return () => { clearTimeout(start); clearTimeout(timeout); controller.abort(); };
  }, [firmwareId, sourceUrl, repoId, catalogTime, key]);

  const value = result?.key === key ? result?.value : null;
  const overlay = value?.github;
  const counts = overlay ?? firmware.popularity;
  if (!counts || (counts.stars == null && counts.forks == null)) return null;
  return (
    <p className="firmware-popularity">
      {counts.stars != null && <><span className="firmware-popularity-figure">{counts.stars}</span> stars</>}
      {counts.forks != null && <>{counts.stars != null && " · "}<span className="firmware-popularity-figure">{counts.forks}</span> forks</>}
      <span className="popularity-glance-scope">
        {value?.github ? <>{repositorySnapshot({ github_as_of: value.github.observed_at })} · {OUTCOME_LABEL[value.outcome]}</>
          : repositorySnapshot(firmware.popularity ?? {})}
      </span>
      <span className="sr-only" role="status" aria-atomic="true">
        {overlay ? `Repository counts updated: ${overlay.stars} stars and ${overlay.forks} forks.` : ""}
      </span>
    </p>
  );
}
