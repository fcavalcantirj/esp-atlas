"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import CompareEmptyState from "@/components/compare/CompareEmptyState";
import ComparePicker, { type PickerType } from "@/components/compare/ComparePicker";
import CompareTable from "@/components/compare/CompareTable";
import { MAX_COMPARE } from "@/components/compare/presets";
import { ApiError, listParts, type PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";

export { MAX_COMPARE };

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

// `initialParts` is the server-rendered /parts list (app/compare/page.tsx). When
// it is present the browser never refetches; when it is empty (the build could
// not reach the API) the client fetches as before.
export default function CompareView({ initialParts = [] }: { initialParts?: PartRecord[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedIds = useMemo(() => parseIds(searchParams.get("ids")), [searchParams]);

  // The server list wins whenever it is present; the client fetch only fills the
  // gap when it is empty. Derived, not copied into state, so a list that arrives
  // in a later render (ISR payload after a router.replace) can never leave the
  // picker stuck on "Loading parts…".
  const needsFetch = initialParts.length === 0;
  const [fetched, setFetched] = useState<PartRecord[] | null>(null);
  const parts = needsFetch ? fetched : initialParts;
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [type, setType] = useState<PickerType>("all");

  useEffect(() => {
    if (!needsFetch) return;
    let cancelled = false;
    listParts()
      .then((r) => {
        if (!cancelled) setFetched(r.results);
      })
      .catch((err) => {
        if (cancelled) return;
        track("api_error", { endpoint: "/parts", status: err instanceof ApiError ? err.status : "network" });
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [needsFetch]);

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
          <CompareEmptyState onPreset={setSelection} />
        )}
      </section>
    </div>
  );
}
