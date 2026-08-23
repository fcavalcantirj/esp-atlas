"use client";

import CompareEmptyState from "@/components/compare/CompareEmptyState";
import ComparePicker from "@/components/compare/ComparePicker";
import { MAX_COMPARE } from "@/components/compare/presets";
import type { PartRecord } from "@/lib/api";

const noop = () => {};

// Suspense fallback for CompareView: the same layout, the same picker over the
// same server-rendered part list, nothing selected. It has the real footprint,
// so hydrating into the interactive view moves nothing (CLS), and it is what
// the static shell ships when the build could not reach the API (empty list →
// the picker shows its own loading line, exactly as before).
export default function ComparePlaceholder({ parts }: { parts: PartRecord[] }) {
  return (
    <div className="compare-layout" aria-busy="true">
      <ComparePicker
        parts={parts.length ? parts : null}
        error={null}
        selectedIds={[]}
        onToggle={noop}
        filter=""
        onFilter={noop}
        type="all"
        onType={noop}
        max={MAX_COMPARE}
      />
      <section aria-label="Comparison">
        <CompareEmptyState onPreset={noop} />
      </section>
    </div>
  );
}
