"use client";

import { useState } from "react";

// The soft entry (SPEC-home-explorer §2, block 2). Phase 1 — what this is —
// routes the typed intent straight into free-text search over the catalogue.
// Phase 2 will send it to Groq to parse into structured filters (the Newcomer
// Wizard), which is gated on the intent->filters contract (SPEC-INDEX G4); the
// input contract here does not change when that lands.
export default function IntentPrompt({
  onSubmit,
  loading,
}: {
  onSubmit: (text: string) => void;
  loading: boolean;
}) {
  const [text, setText] = useState("");
  const trimmed = text.trim();

  return (
    <form
      className="intent-prompt"
      onSubmit={(event) => {
        event.preventDefault();
        if (trimmed) onSubmit(trimmed);
      }}
    >
      <label className="intent-prompt-label" htmlFor="intent-input">
        Tell me what you want to build or run…
      </label>
      <div className="intent-prompt-row">
        <input
          id="intent-input"
          className="intent-prompt-input"
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="a badge with a screen · run Marauder · host a web UI"
          autoComplete="off"
        />
        <button type="submit" className="btn btn--primary" disabled={loading || !trimmed}>
          {loading ? "Searching…" : "Go"}
        </button>
      </div>
      <p className="intent-prompt-hint">…or tap an idea below.</p>
    </form>
  );
}
