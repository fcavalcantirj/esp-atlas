"use client";

import { useEffect, useState } from "react";
import { getStatus, type OverallStatus, type Status } from "@/lib/api";

const REFRESH_MS = 30_000;

const OVERALL_LABEL: Record<OverallStatus, string> = {
  operational: "Operational",
  degraded: "Degraded",
  down: "Down",
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

export default function StatusPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const result = await getStatus();
        if (cancelled) return;
        setStatus(result);
        setError(null);
        setLastChecked(new Date());
      } catch {
        if (cancelled) return;
        setError("Couldn't reach the status endpoint — the API itself may be down.");
        setLastChecked(new Date());
      }
    }

    poll();
    const id = setInterval(poll, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (error && !status) {
    return <p className="status-error">{error}</p>;
  }

  if (!status) {
    return <p className="lead">Checking…</p>;
  }

  return (
    <>
      <div className={`status-banner status-banner--${status.status}`}>
        <span className="status-banner-label">{OVERALL_LABEL[status.status]}</span>
        <span className="status-banner-updated">as of {formatTime(status.generated_at)}</span>
      </div>

      <ul className="status-list">
        {status.components.map((component) => (
          <li key={component.name} className="status-row">
            <span className={`status-dot status-dot--${component.status}`}>{component.status}</span>
            <span className="status-row-name">{component.name}</span>
            <span className="status-row-detail">{component.detail}</span>
          </li>
        ))}
      </ul>

      <p className="status-refresh-note">
        Auto-refreshes every 30s. {lastChecked && <>Last checked {lastChecked.toLocaleTimeString()}.</>}
      </p>
    </>
  );
}
