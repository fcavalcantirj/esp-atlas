import type { Metadata } from "next";
import { Suspense } from "react";
import CompareView from "@/components/compare/CompareView";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

const COMPARE_DESCRIPTION = "Side-by-side, datasheet-verified specs for any ESP32 SoCs, modules and dev boards.";

// The tool is client-rendered from ?ids=, so every ?ids= permutation is the
// same shell: one canonical, kept out of the index, links still followed.
export const metadata: Metadata = {
  title: "Compare",
  description: COMPARE_DESCRIPTION,
  alternates: { canonical: "/compare" },
  robots: { index: false, follow: true },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `Compare · ${SITE_NAME}`,
    description: COMPARE_DESCRIPTION,
    url: "/compare",
    images: [OG_IMAGE],
  },
  twitter: {
    card: "summary_large_image",
    title: `Compare · ${SITE_NAME}`,
    description: COMPARE_DESCRIPTION,
    images: [OG_IMAGE.url],
  },
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
