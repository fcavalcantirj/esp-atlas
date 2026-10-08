"use client";

import { useMemo, useState } from "react";
import FirmwareMatchRow from "@/components/home/FirmwareMatchRow";
import type { Firmware, PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { compatWithChip } from "@/lib/board-compat";
import { rankByIntent } from "@/lib/intent-rank";

// The hero's secondary intent: live, as-you-type ranking over the real
// firmware list (lib/intent-rank.ts) -- no board needed. When a chip has
// already been detected (PlugToFlashHero), each match also carries an honest
// compatibility badge instead of silently hiding what won't run on it.
export default function IntentSearch({
  firmware,
  parts,
  detectedChipFamily = null,
}: {
  firmware: Firmware[];
  parts: PartRecord[];
  detectedChipFamily?: string | null;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => rankByIntent(firmware, query), [firmware, query]);

  function onChange(value: string) {
    setQuery(value);
    if (value.trim().length > 2) track("home_intent_query", { q: value });
  }

  return (
    <div className="intent-search">
      <label className="intent-search-field">
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4-4" />
        </svg>
        <span className="sr-only">Tell us what you want to build</span>
        <input
          type="text"
          value={query}
          onChange={(e) => onChange(e.target.value)}
          placeholder="…or tell us what you want to build"
        />
      </label>
      {query.trim() && (
        <div className="intent-results" aria-live="polite">
          {matches.length === 0 ? (
            <p className="muted">
              No firmware matches &ldquo;{query}&rdquo;. Try a capability — wifi, ble, lora, badusb — or browse the whole
              catalog below.
            </p>
          ) : (
            <ul className="match-list">
              {matches.map((item, index) => (
                <FirmwareMatchRow
                  key={item.id}
                  firmware={item}
                  parts={parts}
                  origin="intent"
                  position={index + 1}
                  chipFamily={detectedChipFamily}
                  compat={detectedChipFamily ? compatWithChip(item, detectedChipFamily) : null}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
