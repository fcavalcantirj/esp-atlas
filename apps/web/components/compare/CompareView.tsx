"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import ComparePicker, { type PickerType } from "@/components/compare/ComparePicker";
import CompareTable from "@/components/compare/CompareTable";
import { ApiError, listParts, type PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";

export const MAX_COMPARE = 6;

const PRESET_COMPARISONS: { label: string; ids: string[] }[] = [
  { label: "C6 vs H2 (smart-home mesh chips)", ids: ["esp32-c6", "esp32-h2"] },
  { label: "The three XIAOs", ids: ["xiao-esp32c3", "xiao-esp32c6", "xiao-esp32s3"] },
  { label: "S3 vs C3 vs classic ESP32", ids: ["esp32-s3", "esp32-c3", "esp32"] },
];

function parseIds(raw: string | null): string[] {
  if (!raw) return [];
  const seen = new Set<string>();
  for (const id of raw.split(",")) {
    const trimmed = id.trim();
    if (trimmed && !seen.has(trimmed)) seen.add(trimmed);
    if (seen.size >= MAX_COMPARE) break;
  }
  return [...seen];
}

export default function CompareView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedIds = useMemo(() => parseIds(searchParams.get("ids")), [searchParams]);

  const [parts, setParts] = useState<PartRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [type, setType] = useState<PickerType>("all");

  useEffect(() => {
    let cancelled = false;
    listParts()
      .then((r) => {
        if (!cancelled) setParts(r.results);
      })
      .catch((err) => {
        if (cancelled) return;
        track("api_error", { endpoint: "/parts", status: err instanceof ApiError ? err.status : "network" });
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const idsKey = selectedIds.join(",");
  useEffect(() => {
    if (selectedIds.length >= 2) track("compare_view", { part_ids: idsKey, count: selectedIds.length });
    // idsKey captures the selection; selectedIds itself is derived from it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  const setSelection = useCallback(
    (ids: string[]) => {
      const query = ids.length ? `?ids=${ids.map(encodeURIComponent).join(",")}` : "";
      router.replace(`${pathname}${query}`, { scroll: false });
    },
    [router, pathname],
  );

  function toggle(id: string) {
    if (selectedIds.includes(id)) {
      track("compare_remove", { part_id: id, selected_count: selectedIds.length - 1 });
      setSelection(selectedIds.filter((x) => x !== id));
    } else if (selectedIds.length < MAX_COMPARE) {
      track("compare_add", { part_id: id, selected_count: selectedIds.length + 1 });
      setSelection([...selectedIds, id]);
    }
  }

  function onFilter(next: string) {
    setFilter(next);
    if (next.trim()) track("compare_filter", { q: next.trim(), type });
  }

  function onType(next: PickerType) {
    setType(next);
    track("compare_filter", { q: filter.trim(), type: next });
  }

  const byId = useMemo(() => new Map((parts ?? []).map((p) => [p.id, p])), [parts]);
  const selectedParts = selectedIds.map((id) => byId.get(id)).filter((p): p is PartRecord => Boolean(p));

  return (
    <div className="compare-layout">
      <ComparePicker
        parts={parts}
        error={error}
        selectedIds={selectedIds}
        onToggle={toggle}
        filter={filter}
        onFilter={onFilter}
        type={type}
        onType={onType}
        max={MAX_COMPARE}
      />
      <section aria-label="Comparison" aria-live="polite">
        {selectedParts.length >= 1 ? (
          <CompareTable parts={selectedParts} onRemove={toggle} onClear={() => setSelection([])} />
        ) : (
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
                    setSelection(preset.ids);
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
