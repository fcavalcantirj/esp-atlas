"use client";

import { useMemo } from "react";
import type { PartRecord } from "@/lib/api";
import { brandLabel } from "@/lib/brand";
import { typePlural } from "@/lib/format";

export type PickerType = "all" | "board" | "module" | "soc";

const TYPE_ORDER: Exclude<PickerType, "all">[] = ["board", "module", "soc"];

interface ComparePickerProps {
  parts: PartRecord[] | null;
  error: string | null;
  selectedIds: string[];
  onToggle: (id: string) => void;
  filter: string;
  onFilter: (value: string) => void;
  type: PickerType;
  onType: (value: PickerType) => void;
  max: number;
}

// Narrows the already-loaded /parts list for picking. This is a UI convenience
// over a list the API already returned in full — not search ranking, which
// stays in esp_atlas_core.
function matches(part: PartRecord, needle: string): boolean {
  if (!needle) return true;
  const haystack = `${part.name} ${part.id} ${brandLabel(part)} ${part.soc_ref ?? ""} ${part.form_factor ?? ""}`.toLowerCase();
  return needle
    .toLowerCase()
    .split(/\s+/)
    .every((token) => haystack.includes(token));
}

export default function ComparePicker({
  parts,
  error,
  selectedIds,
  onToggle,
  filter,
  onFilter,
  type,
  onType,
  max,
}: ComparePickerProps) {
  const needle = filter.trim();
  const full = selectedIds.length >= max;

  const groups = useMemo(() => {
    const list = (parts ?? []).filter((p) => (type === "all" || p.type === type) && matches(p, needle));
    return TYPE_ORDER.map((t) => {
      const items = list.filter((p) => p.type === t);
      const brands = new Map<string, PartRecord[]>();
      for (const item of items) {
        const key = brandLabel(item);
        const arr = brands.get(key) ?? [];
        arr.push(item);
        brands.set(key, arr);
      }
      return { type: t, items, brands: [...brands.entries()].sort(([a], [b]) => a.localeCompare(b)) };
    }).filter((g) => g.items.length > 0);
  }, [parts, type, needle]);

  const option = (part: PartRecord) => {
    const checked = selectedIds.includes(part.id);
    return (
      <li key={part.id}>
        <label className="compare-option">
          <input
            type="checkbox"
            checked={checked}
            disabled={!checked && full}
            onChange={() => onToggle(part.id)}
            aria-label={`${checked ? "Remove" : "Add"} ${part.name}`}
          />
          <span>{part.name}</span>
          <span className="compare-option-brand">{brandLabel(part)}</span>
        </label>
      </li>
    );
  };

  return (
    <details className="compare-picker compare-picker-mobile" open>
      <summary>
        Pick parts <span className="compare-group-count">({selectedIds.length} of {max} selected)</span>
      </summary>
      <div className="compare-picker-body">
        <input
          type="search"
          placeholder="Filter by name, brand, chip…"
          value={filter}
          onChange={(e) => onFilter(e.target.value)}
          aria-label="Filter parts"
          autoComplete="off"
        />
        <div className="segmented" role="group" aria-label="Part type">
          {(["all", ...TYPE_ORDER] as PickerType[]).map((t) => (
            <button key={t} type="button" aria-pressed={type === t} onClick={() => onType(t)}>
              {t === "all" ? "all" : typePlural(t).toLowerCase()}
            </button>
          ))}
        </div>
        {full && <p className="muted">Maximum of {max} parts — remove one to add another.</p>}
        {error && <p className="error">{error}</p>}
        {parts === null && !error && <p className="muted">Loading parts…</p>}
        {parts !== null && groups.length === 0 && <p className="muted">No parts match that filter.</p>}
        {groups.map((group) => (
          <details key={group.type} className="compare-group" open={needle.length > 0 || group.type !== "board"}>
            <summary>
              {typePlural(group.type)} <span className="compare-group-count">({group.items.length})</span>
            </summary>
            {group.type === "board" && group.brands.length > 1 ? (
              group.brands.map(([brand, items]) => (
                <details key={brand} className="compare-group" open={needle.length > 0}>
                  <summary>
                    {brand} <span className="compare-group-count">({items.length})</span>
                  </summary>
                  <ul className="compare-options">{items.map(option)}</ul>
                </details>
              ))
            ) : (
              <ul className="compare-options">{group.items.map(option)}</ul>
            )}
          </details>
        ))}
      </div>
    </details>
  );
}
