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
import { parseIntent, type Example, type IntentParse, type NeedsExample } from "@/lib/api";
import { useExplorer } from "@/lib/use-explorer";
import { useRouter } from "next/navigation";
import { useState } from "react";

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
  const router = useRouter();
  // What the intent box understood about the last thing typed. Kept beside the
  // results so the user can see the parse and correct it, rather than guessing
  // why they got what they got.
  const [parse, setParse] = useState<IntentParse | null>(null);
  const [parsing, setParsing] = useState(false);

  function onExample(example: NeedsExample) {
    track("example_click", { example: example.id, kind: "needs" });
    setNeeds(example.needs);
    void executeWizard(example.needs, scrollToResults);
  }

  async function onIntent(text: string) {
    setParsing(true);
    setParse(null);
    try {
      const parsed = await parseIntent(text);
      setParse(parsed);
      track("intent_parse", { q: text, kind: parsed.kind, cached: parsed.cached });

      if (parsed.kind === "firmware" && parsed.firmware) {
        // The recipe graph already answers this better than any filter could.
        router.push(`/firmware/${encodeURIComponent(parsed.firmware)}`);
        return;
      }
      if (parsed.kind === "filters") {
        setNeeds(parsed.filters);
        void executeWizard(parsed.filters, scrollToResults);
        return;
      }
      // Unreadable: fall back to keyword search, but say so — never pass a
      // keyword dump off as understanding.
      const next = { q: text };
      setFilters(next);
      void executeSearch(next, scrollToResults);
    } catch {
      // Inference unavailable (no key, rate-limited). The prompt must still work.
      setParse(null);
      const next = { q: text };
      setFilters(next);
      void executeSearch(next, scrollToResults);
    } finally {
      setParsing(false);
    }
  }

  return (
    <div className="home">
      <IntentPrompt onSubmit={(text) => void onIntent(text)} loading={state.loading || parsing} />

      {parse && (parse.understood.length > 0 || parse.unmapped.length > 0 || parse.kind === "unreadable") && (
        <div className="intent-parse" aria-live="polite">
          {parse.understood.length > 0 && (
            <p className="intent-parse-row">
              <span className="intent-parse-label">Understood</span>
              {parse.understood.map((text) => (
                <span className="chip chip--accent" key={text}>
                  {text}
                </span>
              ))}
            </p>
          )}
          {parse.kind === "unreadable" && (
            <p className="intent-parse-note">
              I couldn&apos;t read that as a build goal, so these are keyword matches instead.
            </p>
          )}
          {parse.unmapped.length > 0 && (
            <p className="intent-parse-note">
              No field for {parse.unmapped.join(", ")} in the atlas yet — results don&apos;t account for that.
            </p>
          )}
        </div>
      )}

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
