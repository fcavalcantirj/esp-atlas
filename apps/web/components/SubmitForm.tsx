"use client";

import { useEffect, useRef, useState } from "react";

// Cloudflare Turnstile renders into #turnstile-slot once its script (loaded by the page) is ready.
declare global {
  interface Window {
    turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => string; reset: (id?: string) => void };
  }
}

type Result = { issue_url: string; issue: number; existing: boolean } | { error: string } | null;

export default function SubmitForm({ siteKey }: { siteKey: string | undefined }) {
  const [repo, setRepo] = useState("");
  const [boards, setBoards] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);
  const slot = useRef<HTMLDivElement | null>(null);
  const widget = useRef<string | null>(null);

  useEffect(() => {
    if (!siteKey || !slot.current) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (window.turnstile && slot.current && widget.current === null) {
        widget.current = window.turnstile.render(slot.current, {
          sitekey: siteKey,
          callback: (t: string) => setToken(t),
          "expired-callback": () => setToken(null),
          "error-callback": () => setToken(null),
        });
        clearInterval(timer);
      } else if (tries > 100) {
        clearInterval(timer);
      }
    }, 100);
    return () => clearInterval(timer);
  }, [siteKey]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/api/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ repo, boards, turnstile: token ?? "" }),
      });
      const data = (await res.json()) as Result;
      setResult(data);
      if (window.turnstile && widget.current !== null) {
        window.turnstile.reset(widget.current);
        setToken(null);
      }
    } catch {
      setResult({ error: "the request did not reach the site; try again" });
    } finally {
      setBusy(false);
    }
  }

  if (!siteKey) {
    return (
      <p className="lead">
        The submit box is not switched on in this deployment. Open a{" "}
        <a href="https://github.com/fcavalcantirj/esp-atlas/issues/new?template=submission.yml">submission issue on GitHub</a>{" "}
        instead — it goes through the same gate.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="submit-form" aria-describedby="submit-help">
      <label htmlFor="submit-repo">GitHub repository URL</label>
      <input id="submit-repo" name="repo" type="url" inputMode="url" required placeholder="https://github.com/owner/repo"
        value={repo} onChange={(e) => setRepo(e.target.value)} autoComplete="off" spellCheck={false} />
      <label htmlFor="submit-boards">Boards it runs on <span className="muted">(optional, comma-separated)</span></label>
      <input id="submit-boards" name="boards" type="text" placeholder="M5Stack Cardputer, LilyGO T-Deck"
        value={boards} onChange={(e) => setBoards(e.target.value)} maxLength={200} />
      <div ref={slot} className="turnstile-slot" aria-label="anti-bot check" />
      <button type="submit" disabled={busy || !repo || !token}>{busy ? "Submitting…" : "Submit"}</button>
      {result && "issue_url" in result && (
        <p role="status" className="submit-ok">
          {result.existing ? "Already submitted — tracked at " : "Submitted — tracked at "}
          <a href={result.issue_url}>issue #{result.issue}</a>. EspAtlas Jr scores it within the hour and comments the verdict there.
        </p>
      )}
      {result && "error" in result && <p role="alert" className="submit-error">{result.error}</p>}
    </form>
  );
}
