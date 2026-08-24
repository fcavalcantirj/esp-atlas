"use client";

// The full spec explorer: the two-column wizard + search layout that used to be
// the home, relocated to /wizard when the home went intent-first (SPEC-home-
// explorer §2). Same state machine as the home, so the two never drift.
import ResultsPanel from "@/components/ResultsPanel";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";
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
