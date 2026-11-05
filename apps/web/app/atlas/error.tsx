"use client";
export default function AtlasError({ reset }: { reset: () => void }) {
  return <main id="main" className="container container--wide" tabIndex={-1}><h1>The atlas couldn’t open.</h1><p>Your selection stays in the address bar.</p><button type="button" className="btn" onClick={reset}>Try again</button></main>;
}
