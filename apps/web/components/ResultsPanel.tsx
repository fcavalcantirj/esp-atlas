"use client";

import type { Ref } from "react";
import Link from "next/link";
import PartResultCard from "@/components/PartResultCard";
import { track } from "@/lib/analytics";
import type { Example, NeedsExample } from "@/lib/api";
import type { ExplorerState } from "@/lib/explorer";

const NEED_LABELS: Record<string, string> = {
  form: "form factor",
  budget: "budget",
  ieee802154: "smart-home mesh",
  usb_native: "native USB",
  radio: "Wi-Fi",
  band: "band",
  type: "type",
  protocol: "protocol",
  ble: "BLE",
  bt_classic: "BT Classic",
  q: "text",
  soc: "SoC",
  module: "module",
};

// The toggle sets psram_min to exactly this value; its chip reads as the
// friendly "can host a web server" claim instead of the raw MB threshold.
const HOSTING_LANE_PSRAM_MIN = 2;

function activeChips(query: ExplorerState["lastQuery"]): { key: string; label: string }[] {
  if (!query) return [];
  const source = (query.kind === "wizard" ? query.needs : query.filters) as Record<string, unknown>;
  return Object.entries(source)
    .filter(([, value]) => value !== undefined && value !== "" && value !== false && value !== null)
    .map(([key, value]) => {
      const label = NEED_LABELS[key] ?? key;
      if (value === true) return { key, label };
      if (key === "band") return { key, label: `${label}: ${String(value)} GHz` };
      if (key === "q") return { key, label: `"${String(value)}"` };
      if (key === "psram_min") {
        return value === HOSTING_LANE_PSRAM_MIN
          ? { key, label: "Can host a web server" }
          : { key, label: `PSRAM >= ${String(value)} MB` };
      }
      if (key === "flash_min") return { key, label: `Flash >= ${String(value)} MB` };
      return { key, label: `${label}: ${String(value)}` };
    });
}

interface ResultsPanelProps {
  state: ExplorerState;
  examples: Example[];
  onExample: (example: NeedsExample) => void;
  onRelax: (key: string) => void;
  onClear: () => void;
  ref?: Ref<HTMLElement>;
}

export default function ResultsPanel({ state, examples, onExample, onRelax, onClear, ref }: ResultsPanelProps) {
  const { results, loading, error, lastQuery } = state;
  const origin = lastQuery?.kind ?? null;
  const chips = activeChips(lastQuery);

  return (
    <section className="home-results" ref={ref} aria-label="Results" aria-live="polite" aria-busy={loading}>
      {lastQuery === null && !loading && (
        <div className="empty-state">
          <h2>Start with a question</h2>
          <p>
            Tell the wizard what matters and get every part in the atlas that fits, with the reason it matched.
            {examples.length > 0 && " Or start from one of these — generated from the data, so the list never goes stale:"}
          </p>
          {examples.length > 0 && (
            <div className="preset-row">
              {examples.map((example) =>
                example.kind === "firmware" ? (
                  <Link
                    key={example.id}
                    href={`/firmware/${encodeURIComponent(example.firmware)}`}
                    className="chip chip--button"
                    onClick={() => track("example_click", { example: example.id, kind: "firmware" })}
                  >
                    {example.label}
                  </Link>
                ) : (
                  <button
                    key={example.id}
                    type="button"
                    className="chip chip--button"
                    onClick={() => onExample(example)}
                  >
                    {example.label}
                  </button>
                ),
              )}
            </div>
          )}
        </div>
      )}

      {loading && <p className="results-loading">Searching…</p>}

      {error && (
        <div className="empty-state">
          <h2>The API did not answer</h2>
          <p className="error mono">{error}</p>
          <p>Try again in a moment — the dataset itself lives on GitHub and is fine.</p>
        </div>
      )}

      {results && (
        <>
          <div className="results-header">
            <span className="results-count">
              {results.length === 0
                ? "No parts match"
                : `${results.length} part${results.length === 1 ? "" : "s"} match`}
            </span>
            {origin && <span className="results-origin">via {origin}</span>}
            {chips.length > 0 && (
              <div className="chip-row">
                {chips.map((chip) => (
                  <span key={chip.key} className="chip chip--accent">
                    {chip.label}
                    <button
                      type="button"
                      className="chip-remove"
                      aria-label={`Remove ${chip.label}`}
                      title="Remove this filter and search again"
                      onClick={() => onRelax(chip.key)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="results-actions">
              <button type="button" className="btn btn--sm" onClick={onClear}>
                Clear
              </button>
            </div>
          </div>

          {results.length === 0 && (
            <div className="empty-state">
              <h2>Nothing in the atlas matches all of that yet</h2>
              <p>
                Some combinations are honestly impossible (a Wi-Fi-4-only form factor with Wi-Fi 6, for example); others
                just aren&apos;t covered yet. Drop one filter to widen the search:
              </p>
              {chips.length > 0 && (
                <div className="preset-row">
                  {chips.map((chip) => (
                    <button key={chip.key} type="button" className="chip chip--button" onClick={() => onRelax(chip.key)}>
                      Drop {chip.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {results.length > 0 && (
            <ul className="results-list">
              {results.map((part, index) => (
                <PartResultCard key={part.id} part={part} origin={origin ?? "search"} position={index + 1} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
