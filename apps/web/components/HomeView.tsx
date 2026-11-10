"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import BuildGuideAnswer from "@/components/BuildGuideAnswer";
import ExamplesGrid from "@/components/ExamplesGrid";
import IntentPrompt from "@/components/IntentPrompt";
import ResultsPanel from "@/components/ResultsPanel";
import RunGuideAnswer from "@/components/RunGuideAnswer";
import SearchBox from "@/components/SearchBox";
import WizardForm from "@/components/WizardForm";
import { newAnalyticsAttemptId, track } from "@/lib/analytics";
import { ApiError, buildGuide, parseIntent, runGuide, type BuildGuide, type Example, type IntentParse,
  type NeedsExample, type RunGuideResponse, type WizardNeeds } from "@/lib/api";
import { useExplorer } from "@/lib/use-explorer";

const UNMAPPED_CLARIFIERS: { label: string; needs: WizardNeeds }[] = [
  { label: "Battery", needs: { battery: true } }, { label: "Wi-Fi", needs: { radio: "wifi-4" } },
  { label: "Cheap", needs: { budget: "cheap" } }, { label: "Native USB", needs: { usb_native: true } },
];
const NO_SCROLL = () => {};
type Attempt = { id: number; text: string };
type Answer = { kind: "idle" }
  | (Attempt & { kind: "parsing" })
  | (Attempt & { kind: "boards"; fallback?: string })
  | (Attempt & { kind: "firmware"; firmware: string; name?: string; loading: boolean; data?: RunGuideResponse; error?: string })
  | (Attempt & { kind: "build"; loading: boolean; data?: BuildGuide; error?: string });
const message = (error: unknown) => error instanceof Error ? error.message : "The request failed. Please try again.";

export default function HomeView({ examples }: { examples: Example[] }) {
  const { facets, needs, setNeeds, filters, setFilters, state, resultsRef, executeWizard,
    executeSearch, onRelax, onClear } = useExplorer();
  const [answer, setAnswer] = useState<Answer>({ kind: "idle" });
  const [parse, setParse] = useState<IntentParse | null>(null);
  const current = useRef(0);
  const answerRef = useRef<HTMLElement>(null);
  const answerId = answer.kind === "idle" ? 0 : answer.id;
  const busy = answer.kind === "parsing" || ("loading" in answer && answer.loading)
    || (answer.kind === "boards" && state.loading);

  // A submission, including a repeated query, owns one stable answer region.
  // Move focus once at submission, never again when a late response arrives.
  useEffect(() => {
    if (!answerId) return;
    answerRef.current?.focus({ preventScroll: true });
    answerRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
  }, [answerId]);
  useEffect(() => () => { current.current += 1; }, []);

  const begin = useCallback((text: string, kind: "parsing" | "boards"): Attempt => {
    const attempt = { id: ++current.current, text };
    onClear();
    setParse(null);
    setAnswer({ ...attempt, kind });
    return attempt;
  }, [onClear]);
  function clear() {
    current.current += 1;
    setAnswer({ kind: "idle" });
    setParse(null);
    onClear();
    document.getElementById("intent-input")?.focus();
  }
  function onExample(example: NeedsExample) {
    track("example_click", { example: example.id, kind: "needs" });
    begin("", "boards");
    setNeeds(example.needs);
    void executeWizard(example.needs, NO_SCROLL);
  }
  function onClarifier(extra: WizardNeeds) {
    track("intent_clarifier_click", { extra: JSON.stringify(extra) });
    begin("", "boards");
    setNeeds(extra);
    void executeWizard(extra, NO_SCROLL);
  }
  function relax(key: string) {
    begin("", "boards");
    onRelax(key, NO_SCROLL);
  }

  const loadGuide = useCallback(async (attempt: Attempt, parsed: IntentParse, attemptId: string) => {
    const started = performance.now();
    const kind = parsed.kind === "firmware" ? "run" : "build";
    track("guide_submit", { attempt_id: attemptId, surface: "home", kind });
    try {
      if (parsed.kind === "firmware" && parsed.firmware) {
        const data = await runGuide(parsed.firmware);
        if (current.current !== attempt.id) return;
        setAnswer({ ...attempt, kind: "firmware", firmware: parsed.firmware, name: parsed.firmware_name, loading: false, data });
      } else {
        const data = await buildGuide(attempt.text);
        if (current.current !== attempt.id) return;
        setAnswer({ ...attempt, kind: "build", loading: false, data });
      }
      track("guide_result", { attempt_id: attemptId, surface: "home", kind, outcome: "success", latency_ms: Math.round(performance.now() - started) });
    } catch (error) {
      if (current.current !== attempt.id) return;
      setAnswer(parsed.kind === "firmware" && parsed.firmware
        ? { ...attempt, kind: "firmware", firmware: parsed.firmware, name: parsed.firmware_name, loading: false, error: message(error) }
        : { ...attempt, kind: "build", loading: false, error: message(error) });
      track("guide_error", { attempt_id: attemptId, surface: "home", kind, outcome: "error",
        fallback: kind === "build" ? "search" : undefined, status: error instanceof ApiError ? error.status : "network",
        latency_ms: Math.round(performance.now() - started) });
    }
  }, []);

  const onIntent = useCallback(async (text: string) => {
    const started = performance.now();
    const attemptId = newAnalyticsAttemptId();
    const attempt = begin(text, "parsing");
    track("intent_submit", { attempt_id: attemptId, surface: "home", q_length: text.length });
    try {
      const parsed = await parseIntent(text);
      if (current.current !== attempt.id) return;
      setParse(parsed);
      track("intent_parse", { attempt_id: attemptId, q: text, kind: parsed.kind, cached: parsed.cached });
      const fallback = parsed.kind === "unreadable" || (parsed.kind === "firmware" && !parsed.firmware);
      track("intent_result", { attempt_id: attemptId, surface: "home", kind: parsed.kind,
        outcome: fallback ? "fallback" : parsed.kind === "unmapped" ? "unmapped" : "success",
        fallback: fallback ? "search" : parsed.kind === "unmapped" ? "build_guide" : undefined,
        latency_ms: Math.round(performance.now() - started) });
      if (parsed.kind === "firmware" && parsed.firmware) {
        setAnswer({ ...attempt, kind: "firmware", firmware: parsed.firmware, name: parsed.firmware_name, loading: true });
        void loadGuide(attempt, parsed, attemptId);
      } else if (parsed.kind === "filters") {
        setAnswer({ ...attempt, kind: "boards" });
        setNeeds(parsed.filters);
        void executeWizard(parsed.filters, NO_SCROLL, attemptId);
      } else if (parsed.kind === "unmapped") {
        setAnswer({ ...attempt, kind: "build", loading: true });
        void loadGuide(attempt, parsed, attemptId);
        setFilters({ q: text });
        void executeSearch({ q: text }, NO_SCROLL, attemptId);
      } else {
        setAnswer({ ...attempt, kind: "boards", fallback: "I couldn't read that as a build goal. These are keyword matches instead." });
        setFilters({ q: text });
        void executeSearch({ q: text }, NO_SCROLL, attemptId);
      }
    } catch {
      if (current.current !== attempt.id) return;
      track("intent_error", { attempt_id: attemptId, surface: "home", stage: "parse", outcome: "error", fallback: "search", latency_ms: Math.round(performance.now() - started) });
      setAnswer({ ...attempt, kind: "boards", fallback: "The request interpreter is unavailable. These are keyword matches instead." });
      setFilters({ q: text });
      void executeSearch({ q: text }, NO_SCROLL, attemptId);
    }
  }, [begin, executeSearch, executeWizard, loadGuide, setFilters, setNeeds]);

  function retryBoards() {
    const query = state.lastQuery;
    if (!query) return;
    begin(query.kind === "search" ? query.filters.q || "" : "", "boards");
    if (query.kind === "search") void executeSearch(query.filters, NO_SCROLL);
    else void executeWizard(query.needs, NO_SCROLL);
  }

  const status = answer.kind === "idle" ? "" : answer.kind === "parsing" ? "Reading your request…"
    : answer.kind === "boards" ? state.loading ? "Searching the catalog…" : state.error ? "The results could not be loaded."
      : state.results ? `${state.results.length} part${state.results.length === 1 ? "" : "s"} match.` : "Preparing results…"
    : answer.loading ? answer.kind === "firmware" ? "Finding recorded recipes…" : "Working out what you need…"
    : answer.error ? "The guide could not be loaded. You can try again." : "Your guide is ready.";

  return (
    <div className="home">
      <IntentPrompt onSubmit={text => void onIntent(text)} loading={busy} />
      {/* Announce outside aria-busy; the answer shows the loading message once. */}
      <p className={status && !busy ? "home-answer-status" : "sr-only"} role="status" aria-atomic="true">{status}</p>
      {answer.kind === "idle" ? <ExamplesGrid examples={examples} /> : (
        <section className="home-answer" ref={answerRef} tabIndex={-1} aria-label="Your atlas answer" aria-busy={busy}>
          {answer.kind === "parsing" && <p className="results-loading" aria-hidden="true">{status}</p>}
          {parse && (parse.understood.length > 0 || (parse.kind === "filters" && parse.unmapped.length > 0)) && (
            <div className="intent-parse">
              {parse.understood.length > 0 && <p className="intent-parse-row"><span className="intent-parse-label">Understood</span>
                {parse.understood.map(text => <span className="chip chip--accent" key={text}>{text}</span>)}</p>}
              {parse.kind === "filters" && parse.unmapped.length > 0 && <p className="intent-parse-note">No field for {parse.unmapped.join(", ")} in the atlas yet — results don&apos;t account for that.</p>}
            </div>
          )}
          {(answer.kind === "firmware" || answer.kind === "build") && (
            <div className="home-results">
              {answer.loading && <p className="results-loading" aria-hidden="true">{status}</p>}
              {answer.error && <div className="empty-state"><h2>We couldn&apos;t load this guide</h2><p>{answer.error}</p>
                <button type="button" className="btn" onClick={() => void onIntent(answer.text)}>Try again</button></div>}
              {answer.kind === "firmware" && answer.data && <RunGuideAnswer guide={answer.data} />}
              {answer.kind === "build" && answer.data && <BuildGuideAnswer guide={answer.data} />}
              {answer.kind === "firmware" && <p><Link href={`/firmware/${encodeURIComponent(answer.firmware)}`} className="example-group-seeall"
                onClick={() => track("shelf_see_all", { shelf: "firmware_page", href: `/firmware/${answer.firmware}` })}>
                See the full {answer.name || answer.firmware} page ›</Link></p>}
              {answer.kind === "build" && <p className="intent-parse-row"><span className="intent-parse-label">Or narrow by spec</span>
                {UNMAPPED_CLARIFIERS.map(c => <button key={c.label} type="button" className="chip chip--button" onClick={() => onClarifier(c.needs)}>{c.label}</button>)}</p>}
            </div>
          )}
          {answer.kind === "build" && <details className="intent-secondary-results" key={answer.id}>
            <summary>or browse keyword matches</summary>
            <ResultsPanel ref={resultsRef} state={state} onExample={onExample} onRelax={relax} onClear={clear} />
          </details>}
          {answer.kind === "boards" && <>
            {answer.fallback && <p className="intent-parse-note">{answer.fallback}</p>}
            <ResultsPanel ref={resultsRef} state={state} onExample={onExample} onRelax={relax} onClear={clear} />
            {state.error && <button type="button" className="btn" onClick={retryBoards}>Try again</button>}
          </>}
        </section>
      )}
      <details className="panel spec-wizard" onToggle={event => track("advanced_filters_toggle", { panel: "spec_wizard", open: event.currentTarget.open })}>
        <summary className="spec-wizard-summary"><span>Spec wizard</span><span className="spec-wizard-open">Open ›</span></summary>
        <p className="panel-hint">Know the specs you need? Filter the catalogue directly — or open the <a href="/wizard">full wizard page</a>.</p>
        <WizardForm facets={facets} value={needs} onChange={setNeeds} loading={busy}
          onSubmit={() => { begin("", "boards"); void executeWizard(needs, NO_SCROLL); }} />
        <div className="spec-wizard-search"><h3 className="panel-title">Search</h3>
          <p className="panel-hint">Know the name or a keyword? Free text plus exact filters.</p>
          <SearchBox facets={facets} value={filters} onChange={setFilters} loading={busy}
            onSubmit={() => { begin(filters.q || "", "boards"); void executeSearch(filters, NO_SCROLL); }} />
        </div>
      </details>
    </div>
  );
}
