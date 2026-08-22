import type { Metadata } from "next";
import { Suspense } from "react";
import CompareView from "@/components/compare/CompareView";

export const metadata: Metadata = {
  title: "Compare",
  description: "Side-by-side, datasheet-verified specs for any ESP32 SoCs, modules and dev boards.",
};

export default function ComparePage() {
  return (
    <main id="main" className="container container--wide" tabIndex={-1}>
      <h1>Compare</h1>
      <p className="lead">Pick two to six parts; differing rows are highlighted. The URL updates, so a comparison can be shared.</p>
      {/* useSearchParams inside CompareView needs a Suspense boundary for the static shell */}
      <Suspense fallback={<p className="muted">Loading parts…</p>}>
        <CompareView />
      </Suspense>
    </main>
  );
}
