"use client";

// The explorer state machine: facets, the current wizard needs / search filters,
// the last query and its results. Both surfaces that can run a query share it —
// the intent-first home and the full /wizard page — so the two never drift.
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
import type { ExplorerState } from "@/lib/explorer";

const INITIAL_STATE: ExplorerState = { results: null, loading: false, error: null, lastQuery: null };

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function reportApiError(endpoint: string, err: unknown) {
  track("api_error", { endpoint, status: err instanceof ApiError ? err.status : "network" });
}

export function useExplorer() {
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

  const scrollToResults = useCallback(() => {
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const scrollToResultsOnMobile = useCallback(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) scrollToResults();
  }, [scrollToResults]);

  const executeWizard = useCallback(
    async (wizardNeeds: WizardNeeds, onDone?: () => void) => {
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
      (onDone ?? scrollToResultsOnMobile)();
    },
    [scrollToResultsOnMobile],
  );

  const executeSearch = useCallback(
    async (searchFilters: SearchFilters, onDone?: () => void) => {
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
        track(results.length ? "search_results" : "search_empty", {
          q,
          filters: filtersStr,
          result_count: results.length,
        });
      } catch (err) {
        reportApiError("/search", err);
        setState({
          results: null,
          loading: false,
          error: errorMessage(err),
          lastQuery: { kind: "search", filters: searchFilters },
        });
      }
      (onDone ?? scrollToResultsOnMobile)();
    },
    [scrollToResultsOnMobile],
  );

  const onRelax = useCallback(
    (key: string) => {
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
    },
    [state.lastQuery, executeWizard, executeSearch],
  );

  const onClear = useCallback(() => setState(INITIAL_STATE), []);

  return {
    facets,
    needs,
    setNeeds,
    filters,
    setFilters,
    state,
    resultsRef,
    executeWizard,
    executeSearch,
    scrollToResults,
    onRelax,
    onClear,
  };
}
