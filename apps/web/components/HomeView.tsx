"use client";

// The intent-first home (SPEC-home-explorer §2, locked 2026-08-24): the prompt
// and the generated examples lead; the spec wizard is a drawer below them, and
// also lives in full at /wizard. Results only appear once something is asked.
import Link from "next/link";
import ExamplesGrid from "@/components/ExamplesGrid";
import IntentPrompt from "@/components/IntentPrompt";
import ResultsPanel from "@/components/ResultsPanel";
import RunGuideAnswer from "@/components/RunGuideAnswer";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";
import { track } from "@/lib/analytics";
import {
  ApiError,
  parseIntent,
  runGuide,
  type Example,
  type IntentParse,
  type NeedsExample,
  type RunGuideResponse,
  type WizardNeeds,
} from "@/lib/api";
import { useExplorer } from "@/lib/use-explorer";
import { useState } from "react";

// The catalogue has no field for what an "unmapped" goal names (a sensor,
// camera, motor...) -- these are the real board constraints a maker can add
// instead, each a one-tap replay of the wizard (SPEC-home-explorer §2).
const UNMAPPED_CLARIFIERS: { label: string; needs: WizardNeeds }[] = [
  { label: "Battery", needs: { battery: true } },
  { label: "Wi-Fi", needs: { radio: "wifi-4" } },
  { label: "Cheap", needs: { budget: "cheap" } },
  { label: "Native USB", needs: { usb_native: true } },
];

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
  // What the intent box understood about the last thing typed. Kept beside the
  // results so the user can see the parse and correct it, rather than guessing
  // why they got what they got.
  const [parse, setParse] = useState<IntentParse | null>(null);
  const [parsing, setParsing] = useState(false);
  // The firmware branch answers inline (the grounded run_guide teaching), never
  // navigates away — this is that answer, resolved from GET /run/{firmware_id}.
  const [guide, setGuide] = useState<RunGuideResponse | null>(null);
  const [guideLoading, setGuideLoading] = useState(false);
  const [guideError, setGuideError] = useState<string | null>(null);

  function onExample(example: NeedsExample) {
    track("example_click", { example: example.id, kind: "needs" });
    setNeeds(example.needs);
    void executeWizard(example.needs, scrollToResults);
  }

  // An "unmapped" parse understood the goal but has no board field for it --
  // this replays the wizard with a real constraint added, promoting the
  // secondary keyword matches out of the way with an actual answer.
  function onClarifier(extra: WizardNeeds) {
    track("intent_clarifier_click", { extra: JSON.stringify(extra) });
    setParse(null);
    setNeeds(extra);
    void executeWizard(extra, scrollToResults);
  }

  async function loadRunGuide(firmwareId: string) {
    setGuideLoading(true);
    setGuideError(null);
    try {
      setGuide(await runGuide(firmwareId));
    } catch (err) {
      setGuide(null);
      setGuideError(err instanceof ApiError ? err.message : "The API did not answer in time.");
    } finally {
      setGuideLoading(false);
    }
  }

  async function onIntent(text: string) {
    setParsing(true);
    setParse(null);
    setGuide(null);
    setGuideError(null);
    try {
      const parsed = await parseIntent(text);
      setParse(parsed);
      track("intent_parse", { q: text, kind: parsed.kind, cached: parsed.cached });

      if (parsed.kind === "firmware" && parsed.firmware) {
        // Answer inline, grounded against the recipe graph. The full firmware
        // page stays one click away, never automatic.
        void loadRunGuide(parsed.firmware);
        return;
      }
      if (parsed.kind === "filters") {
        setNeeds(parsed.filters);
        void executeWizard(parsed.filters, scrollToResults);
        return;
      }
      if (parsed.kind === "unmapped") {
        // Groq understood the goal but the atlas has no board field for it --
        // the clarifier chips are the primary answer, so keyword matches run
        // quietly in the background instead of pulling focus down the page.
        const next = { q: text };
        setFilters(next);
        void executeSearch(next);
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

      {parse &&
        (parse.understood.length > 0 || parse.unmapped.length > 0 || parse.kind === "unreadable") && (
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
            {parse.kind === "unmapped" && (
              <>
                <p className="intent-parse-note">
                  Understood: {parse.unmapped.join(", ")} — esp-atlas catalogs boards, not what you build
                  with them, so I can&apos;t narrow this by a board spec alone.
                </p>
                <p className="intent-parse-row">
                  <span className="intent-parse-label">Narrow by</span>
                  {UNMAPPED_CLARIFIERS.map((clarifier) => (
                    <button
                      key={clarifier.label}
                      type="button"
                      className="chip chip--button"
                      onClick={() => onClarifier(clarifier.needs)}
                    >
                      {clarifier.label}
                    </button>
                  ))}
                </p>
              </>
            )}
            {parse.kind === "filters" && parse.unmapped.length > 0 && (
              <p className="intent-parse-note">
                No field for {parse.unmapped.join(", ")} in the atlas yet — results don&apos;t account for
                that.
              </p>
            )}
          </div>
        )}

      {parse && parse.kind === "firmware" && parse.firmware && (
        <section className="home-results" aria-label="Run guide" aria-live="polite" aria-busy={guideLoading}>
          {guideLoading && <p className="results-loading">Working out why…</p>}
          {!guideLoading && guideError && (
            <div className="empty-state">
              <h2>The API did not answer</h2>
              <p className="error mono">{guideError}</p>
              <p>Try again in a moment — the dataset itself lives on GitHub and is fine.</p>
            </div>
          )}
          {!guideLoading && !guideError && guide && <RunGuideAnswer guide={guide} />}
          <p>
            <Link
              href={`/firmware/${encodeURIComponent(parse.firmware)}`}
              className="example-group-seeall"
              onClick={() => track("shelf_see_all", { shelf: "firmware_page", href: `/firmware/${parse.firmware}` })}
            >
              See the full {parse.firmware_name || parse.firmware} page ›
            </Link>
          </p>
        </section>
      )}

      {asked && parse?.kind === "unmapped" && (
        <details className="intent-secondary-results">
          <summary>or browse keyword matches</summary>
          <ResultsPanel ref={resultsRef} state={state} onExample={onExample} onRelax={onRelax} onClear={onClear} />
        </details>
      )}
      {asked && parse?.kind !== "unmapped" && (
        <ResultsPanel ref={resultsRef} state={state} onExample={onExample} onRelax={onRelax} onClear={onClear} />
      )}

      <ExamplesGrid examples={examples} />

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
