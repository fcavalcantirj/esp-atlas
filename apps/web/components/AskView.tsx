"use client";

// The Ask surface (INTERFACE-SPEC "Ask"): a question goes to the API, which
// retrieves matching records and has Groq answer from them at temperature 0.
// The browser never sees the Groq key — it only ever talks to our own API.
import { useState } from "react";
import Link from "next/link";
import { ApiError, askQuestion, type AskAnswer } from "@/lib/api";
import { track } from "@/lib/analytics";

const EXAMPLE_QUESTIONS = [
  "Which ESP32 boards have 8 MB of PSRAM?",
  "What is the difference between the ESP32-C6 and the ESP32-H2?",
  "Which boards can run ESP32 Marauder?",
];

/** One citation per source URL, keeping the first part that cited it. */
function dedupeCitations(answer: AskAnswer) {
  const seen = new Map<string, { part: string; source_url: string }>();
  for (const citation of answer.citations) {
    if (!seen.has(citation.source_url)) {
      seen.set(citation.source_url, { part: citation.part, source_url: citation.source_url });
    }
  }
  return [...seen.values()];
}

export default function AskView() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setQuestion(trimmed);
    setLoading(true);
    setError(null);
    setAnswer(null);
    track("ask_submit", { q: trimmed });
    try {
      const result = await askQuestion(trimmed);
      setAnswer(result);
      track("ask_answer", { q: trimmed, citation_count: result.citations.length, used_count: result.used.length });
    } catch (err) {
      const status = err instanceof ApiError ? err.status : "network";
      // 503 is the deliberate "Groq is not configured or is rate-limited"
      // signal; everything deterministic on the site still works.
      setError(
        status === 503
          ? "Ask is unavailable right now — the wizard and search still work."
          : err instanceof Error
            ? err.message
            : String(err),
      );
      track("ask_error", { q: trimmed, status });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ask">
      <form
        className="ask-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <label className="intent-prompt-label" htmlFor="ask-input">
          Ask about the atlas
        </label>
        <div className="intent-prompt-row">
          <input
            id="ask-input"
            className="intent-prompt-input"
            type="search"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Which ESP32 has the most PSRAM?"
            autoComplete="off"
          />
          <button type="submit" className="btn btn--primary" disabled={loading || !question.trim()}>
            {loading ? "Thinking…" : "Ask"}
          </button>
        </div>
      </form>

      {!answer && !loading && !error && (
        <div className="ask-examples">
          <p className="panel-hint">Not sure what to ask?</p>
          <div className="preset-row">
            {EXAMPLE_QUESTIONS.map((example) => (
              <button key={example} type="button" className="chip chip--button" onClick={() => void submit(example)}>
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && <p className="results-loading">Reading the records…</p>}

      {error && (
        <div className="empty-state">
          <h2>That didn&apos;t work</h2>
          <p className="error mono">{error}</p>
          <p>
            The <Link href="/">wizard</Link> answers the same questions from the data, with no model involved.
          </p>
        </div>
      )}

      {answer && (
        <article className="ask-answer">
          <p className="ask-answer-text">{answer.answer}</p>
          {answer.citations.length > 0 && (
            <section className="ask-sources">
              <h2 className="panel-title">Sources</h2>
              <p className="panel-hint">
                Taken from the records this answer was built from — not from the model&apos;s reply.
              </p>
              <ul className="ask-source-list">
                {dedupeCitations(answer).map((citation) => (
                  <li key={citation.source_url}>
                    <a href={citation.source_url} target="_blank" rel="noopener noreferrer">
                      {citation.part}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </article>
      )}
    </div>
  );
}
