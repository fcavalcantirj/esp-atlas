"use client";

// The intent-first home (SPEC-home-explorer §2, locked 2026-08-24): the prompt
// and the generated examples lead; the spec wizard is a drawer below them, and
// also lives in full at /wizard. Results only appear once something is asked.
import ExamplesGrid from "@/components/ExamplesGrid";
import IntentPrompt from "@/components/IntentPrompt";
import ResultsPanel from "@/components/ResultsPanel";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";
import { track } from "@/lib/analytics";
import type { Example, NeedsExample } from "@/lib/api";
import { useExplorer } from "@/lib/use-explorer";

export default function HomeView({ examples }: { examples: Example[] }) {
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
    scrollToResults,
    onRelax,
    onClear,
  } = useExplorer();

  const asked = state.lastQuery !== null || state.loading;

  function onExample(example: NeedsExample) {
    track("example_click", { example: example.id, kind: "needs" });
    setNeeds(example.needs);
    void executeWizard(example.needs, scrollToResults);
  }

  function onIntent(text: string) {
    const next = { q: text };
    setFilters(next);
    void executeSearch(next, scrollToResults);
  }

  return (
    <div className="home">
      <IntentPrompt onSubmit={onIntent} loading={state.loading} />

      {asked && (
        <ResultsPanel ref={resultsRef} state={state} onExample={onExample} onRelax={onRelax} onClear={onClear} />
      )}

      <ExamplesGrid examples={examples} onExample={onExample} />

      <details
        className="panel spec-wizard"
        onToggle={(event) => track("advanced_filters_toggle", { panel: "spec_wizard", open: event.currentTarget.open })}
      >
        <summary className="spec-wizard-summary">
          <span>Spec wizard</span>
          <span className="spec-wizard-open">Open ›</span>
        </summary>
        <p className="panel-hint">
          Know the specs you need? Filter the catalogue directly — or open the{" "}
          <a href="/wizard">full wizard page</a>.
        </p>
        <WizardForm
          facets={facets}
          value={needs}
          onChange={setNeeds}
          onSubmit={() => void executeWizard(needs, scrollToResults)}
          loading={state.loading}
        />
        <div className="spec-wizard-search">
          <h3 className="panel-title">Search</h3>
          <p className="panel-hint">Know the name or a keyword? Free text plus exact filters.</p>
          <SearchBox
            facets={facets}
            value={filters}
            onChange={setFilters}
            onSubmit={() => void executeSearch(filters, scrollToResults)}
            loading={state.loading}
          />
        </div>
      </details>
    </div>
  );
}
