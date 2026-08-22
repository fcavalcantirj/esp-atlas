"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  getFacets,
  runWizard,
  searchParts,
  type Facets,
  type SearchFilters,
  type WizardNeeds,
} from "@/lib/api";
import { serializeNeeds, track } from "@/lib/analytics";
import ResultsPanel from "@/components/ResultsPanel";
import type { ExplorerState, Preset } from "@/lib/explorer";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";

const INITIAL_STATE: ExplorerState = { results: null, loading: false, error: null, lastQuery: null };

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function reportApiError(endpoint: string, err: unknown) {
  track("api_error", { endpoint, status: err instanceof ApiError ? err.status : "network" });
}

export default function HomeView() {
  const [facets, setFacets] = useState<Facets | null>(null);
  const [needs, setNeeds] = useState<WizardNeeds>({});
  const [filters, setFilters] = useState<SearchFilters>({ q: "" });
  const [state, setState] = useState<ExplorerState>(INITIAL_STATE);
  const resultsRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    getFacets()
      .then((data) => {
        if (!cancelled) setFacets(data);
      })
      .catch((err) => reportApiError("/facets", err));
    return () => {
      cancelled = true;
    };
  }, []);

  const scrollToResultsOnMobile = useCallback(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) {
      resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const executeWizard = useCallback(
    async (wizardNeeds: WizardNeeds) => {
      const needsStr = serializeNeeds(wizardNeeds);
      track("wizard_submit", {
        ...wizardNeeds,
        needs: needsStr,
        needs_count: Object.keys(wizardNeeds).length,
      });
      setState({ results: null, loading: true, error: null, lastQuery: { kind: "wizard", needs: wizardNeeds } });
      try {
        const { results } = await runWizard(wizardNeeds);
        setState({ results, loading: false, error: null, lastQuery: { kind: "wizard", needs: wizardNeeds } });
        track(results.length ? "wizard_results" : "wizard_empty", { needs: needsStr, result_count: results.length });
      } catch (err) {
        reportApiError("/wizard", err);
        setState({
          results: null,
          loading: false,
          error: errorMessage(err),
          lastQuery: { kind: "wizard", needs: wizardNeeds },
        });
      }
      scrollToResultsOnMobile();
    },
    [scrollToResultsOnMobile],
  );

  const executeSearch = useCallback(
    async (searchFilters: SearchFilters) => {
      const { q = "", ...structured } = searchFilters;
      const filtersStr = serializeNeeds(structured);
      track("search_submit", {
        ...structured,
        q,
        filters: filtersStr,
        filter_count: Object.keys(structured).length,
        has_query: q.trim().length > 0,
      });
      setState({ results: null, loading: true, error: null, lastQuery: { kind: "search", filters: searchFilters } });
      try {
        const { results } = await searchParts(searchFilters);
        setState({ results, loading: false, error: null, lastQuery: { kind: "search", filters: searchFilters } });
        track(results.length ? "search_results" : "search_empty", { q, filters: filtersStr, result_count: results.length });
      } catch (err) {
        reportApiError("/search", err);
        setState({
          results: null,
          loading: false,
          error: errorMessage(err),
          lastQuery: { kind: "search", filters: searchFilters },
        });
      }
      scrollToResultsOnMobile();
    },
    [scrollToResultsOnMobile],
  );

  function onPreset(preset: Preset) {
    track("preset_click", { preset: preset.id });
    setNeeds(preset.needs);
    void executeWizard(preset.needs);
  }

  function onRelax(key: string) {
    if (state.lastQuery?.kind === "wizard") {
      const next = { ...state.lastQuery.needs };
      delete next[key as keyof WizardNeeds];
      track("relax_filter", { removed_key: key, needs: serializeNeeds(next) });
      setNeeds(next);
      void executeWizard(next);
    } else if (state.lastQuery?.kind === "search") {
      const next = { ...state.lastQuery.filters };
      delete next[key as keyof SearchFilters];
      if (next.q === undefined) next.q = "";
      track("relax_filter", { removed_key: key, needs: serializeNeeds(next) });
      setFilters(next);
      void executeSearch(next);
    }
  }

  function onClear() {
    setState(INITIAL_STATE);
  }

  return (
    <div className="home-layout">
      <aside className="home-sidebar" aria-label="Find parts">
        <section className="panel" aria-labelledby="wizard-title">
          <h2 className="panel-title" id="wizard-title">
            Wizard
          </h2>
          <p className="panel-hint">What are you building? Answer what matters, skip the rest.</p>
          <WizardForm
            facets={facets}
            value={needs}
            onChange={setNeeds}
            onSubmit={() => void executeWizard(needs)}
            loading={state.loading}
          />
        </section>
        <section className="panel" aria-labelledby="search-title">
          <h2 className="panel-title" id="search-title">
            Search
          </h2>
          <p className="panel-hint">Know the name or a keyword? Free text plus exact filters.</p>
          <SearchBox
            facets={facets}
            value={filters}
            onChange={setFilters}
            onSubmit={() => void executeSearch(filters)}
            loading={state.loading}
          />
        </section>
      </aside>
      <ResultsPanel ref={resultsRef} state={state} onPreset={onPreset} onRelax={onRelax} onClear={onClear} />
    </div>
  );
}
