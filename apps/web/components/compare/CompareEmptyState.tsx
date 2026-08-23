"use client";

import { PRESET_COMPARISONS } from "@/components/compare/presets";
import { track } from "@/lib/analytics";

export default function CompareEmptyState({ onPreset }: { onPreset: (ids: string[]) => void }) {
  return (
    <div className="empty-state">
      <h2>Pick 2–6 parts to compare</h2>
      <p>Use the picker, or start from one of these:</p>
      <div className="preset-row">
        {PRESET_COMPARISONS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            className="chip chip--button"
            onClick={() => {
              track("preset_click", { preset: `compare:${preset.ids.join(",")}` });
              onPreset(preset.ids);
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </div>
  );
}
