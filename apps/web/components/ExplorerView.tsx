"use client";

// The full spec explorer: the two-column wizard + search layout that used to be
// the home, relocated to /wizard when the home went intent-first (SPEC-home-
// explorer §2). Same state machine as the home, so the two never drift.
import ResultsPanel from "@/components/ResultsPanel";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";
import { useEffect, useRef } from "react";
import { track } from "@/lib/analytics";
import type { Example, NeedsExample } from "@/lib/api";
import { useExplorer } from "@/lib/use-explorer";

export default function ExplorerView({ examples }: { examples: Example[] }) {
  const {
    facets,
    needs,
    setNeeds,
    filters,
    setFilters,
    state,
    resultsRef,
    executeWizard,
    executeSearch,
    onRelax,
    onClear,
  } = useExplorer();

  function onExample(example: NeedsExample) {
    track("example_click", { example: example.id, kind: "needs" });
    setNeeds(example.needs);
    void executeWizard(example.needs);
  }

  // A home card is a real link to /wizard?example=<id>: on arrival, run that
  // query so the link lands on its results. Read client-side so the page stays
  // static; an unknown id (a stale link) just shows the empty wizard.
  const ranFromUrl = useRef(false);
  useEffect(() => {
    if (ranFromUrl.current) return;
    const id = new URLSearchParams(window.location.search).get("example");
    if (!id) return;
    const example = examples.find((e): e is NeedsExample => e.kind === "needs" && e.id === id);
    if (!example) return;
    ranFromUrl.current = true;
    track("example_click", { example: example.id, kind: "needs", via: "url" });
    setNeeds(example.needs);
    void executeWizard(example.needs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examples]);

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
      <ResultsPanel
        ref={resultsRef}
        state={state}
        examples={examples}
        onExample={onExample}
        onRelax={onRelax}
        onClear={onClear}
      />
    </div>
  );
}
