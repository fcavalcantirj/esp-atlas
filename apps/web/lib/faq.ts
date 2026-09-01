// Static server HTML + JSON-LD for a soc part page's FAQ section — promoted
// from spike/faq-c6/render.py + jsonld.py (see REPORT.md §(b)/(c)). Plain
// string/object building, not JSX: no client component, no hydration
// boundary, just a fragment concatenated into the page's server-rendered
// HTML (components/part/PartFaq.tsx) and a node spliced into
// structured-data.ts's partGraph() @graph. This module has no "@/" aliased
// runtime imports on purpose (only the type-only FaqItem import below,
// elided at compile time) so it can run under plain `node --test`, unlike
// structured-data.ts which pulls in the rest of the app's alias graph.
import type { FaqItem } from "@/lib/api";

// Mirrors Python's html.escape(quote=True): &/</>/"/' — the FAQ answers are
// server-generated from cited spec data (esp_atlas_core.faq), never user
// input, but escaping is cheap insurance against a stray special character
// in a spec string (e.g. an SoC name) breaking the markup.
export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** <section><details>/<summary> only — no <script>, no event handlers, no component. */
export function renderFaqSection(items: FaqItem[]): string {
  if (items.length === 0) return "";
  const entries = items
    .map(
      (item) =>
        "  <details>\n" +
        `    <summary>${escapeHtml(item.question)}</summary>\n` +
        `    <p>${escapeHtml(item.answer)}</p>\n` +
        "  </details>",
    )
    .join("\n");
  return '<section aria-label="Frequently asked questions">\n' + "  <h2>Frequently asked questions</h2>\n" + `${entries}\n` + "</section>";
}

/**
 * FAQPage node for a soc's grounded Q&A pairs — Google's required shape for
 * the FAQPage rich result: mainEntity is Question[], each with a name and an
 * acceptedAnswer.text. Spliced into structured-data.ts's partGraph() @graph;
 * not a document of its own, so no @context here.
 */
export function faqPage(url: string, items: FaqItem[]) {
  return {
    "@type": "FAQPage" as const,
    "@id": `${url}#faq`,
    mainEntity: items.map((item) => ({
      "@type": "Question" as const,
      name: item.question,
      acceptedAnswer: { "@type": "Answer" as const, text: item.answer },
    })),
  };
}
