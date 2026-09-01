import { renderFaqSection } from "@/lib/faq";
import type { FaqItem } from "@/lib/api";

// Static server HTML only: renderFaqSection returns a plain string (no JSX,
// no client component, no hydration boundary) that this thin wrapper drops
// into the page the same way components/JsonLd.tsx drops in the ld+json
// script tag. Every <details>/<summary> pair here is native, unscripted
// browser behavior — zero bytes of client JS for this section.
export default function PartFaq({ items }: { items: FaqItem[] }) {
  if (items.length === 0) return null;
  return <div dangerouslySetInnerHTML={{ __html: renderFaqSection(items) }} />;
}
