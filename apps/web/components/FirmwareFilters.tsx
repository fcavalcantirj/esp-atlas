"use client";

import Link from "next/link";
import { useRef } from "react";
import { track } from "@/lib/analytics";
import {
  MAX_QUERY, effectiveSort, firmwareSearchParams, isFiltered, optionLabel, socLabel, sortChoices,
  type FirmwareFacets, type FirmwareQuery,
} from "@/lib/firmware-filters";

// SPEC-firmware-search.md §3: a plain GET form, so every state is a URL and the page works with JavaScript
// off (the API filters and orders; this only navigates). "use client" adds three conveniences: a filter
// submits as soon as it changes, empty fields are left out of the URL, and the submit is counted in GA4
// (never the words typed).
export default function FirmwareFilters({ query, facets, results }: { query: FirmwareQuery; facets: FirmwareFacets | null; results: number }) {
  const form = useRef<HTMLFormElement>(null);
  const submit = () => form.current?.requestSubmit();

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    const fields = Array.from(event.currentTarget.elements) as (HTMLInputElement | HTMLSelectElement)[];
    const empty = fields.filter((f) => f.name && (f.type === "checkbox" ? !(f as HTMLInputElement).checked : !f.value.trim()));
    empty.forEach((f) => (f.disabled = true));            // an unset field does not belong in the URL
    setTimeout(() => empty.forEach((f) => (f.disabled = false)), 0);
    track("firmware_search", firmwareSearchParams(query, results));
  }

  const sort = effectiveSort(query);
  return (
    <form ref={form} className="firmware-filters" role="search" method="get" action="/firmware" onSubmit={handleSubmit}>
      <label className="field firmware-filters-q">
        <span className="label-row">Search firmware</span>
        <input type="search" name="q" defaultValue={query.q} maxLength={MAX_QUERY} autoComplete="off"
          placeholder="a name, a board, a feature — e.g. marauder, cardputer, lora" />
      </label>
      <div className="form-grid">
        {facets && (
          <>
            <label className="field">
              <span className="label-row">Runs on board</span>
              <select name="board" defaultValue={query.board} onChange={submit}>
                <option value="">Any board</option>
                {facets.boards.map((o) => <option key={o.id} value={o.id}>{o.name ?? o.id} ({o.count})</option>)}
              </select>
            </label>
            <label className="field">
              <span className="label-row">Chip</span>
              <select name="soc" defaultValue={query.soc} onChange={submit}>
                <option value="">Any chip</option>
                {facets.socs.map((o) => <option key={o.id} value={o.id}>{socLabel(o.id)} ({o.count})</option>)}
              </select>
            </label>
            <label className="field">
              <span className="label-row">Kind</span>
              <select name="category" defaultValue={query.category} onChange={submit}>
                <option value="">Any kind</option>
                {facets.categories.map((o) => <option key={o.id} value={o.id}>{optionLabel(o.id)} ({o.count})</option>)}
              </select>
            </label>
            <label className="field">
              <span className="label-row">Feature</span>
              <select name="capability" defaultValue={query.capability} onChange={submit}>
                <option value="">Any feature</option>
                {facets.capabilities.map((o) => <option key={o.id} value={o.id}>{optionLabel(o.id)} ({o.count})</option>)}
              </select>
            </label>
          </>
        )}
        <label className="field">
          <span className="label-row">Order by</span>
          <select name="sort" defaultValue={query.sort ? sort : ""} onChange={submit}>
            <option value="">{query.q ? "Best match" : "Most stars"}</option>
            {sortChoices(query).filter((o) => o.value !== (query.q ? "relevance" : "popularity")).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="firmware-filters-row">
        <label className="firmware-filters-check">
          <input type="checkbox" name="tested" value="1" defaultChecked={query.tested} onChange={submit} />
          <span>Tested on real hardware</span>
        </label>
        <button type="submit" className="btn btn--primary btn--sm">Search</button>
        {(isFiltered(query) || query.sort !== "") && <Link href="/firmware" className="firmware-filters-clear">Clear all</Link>}
      </div>
    </form>
  );
}
