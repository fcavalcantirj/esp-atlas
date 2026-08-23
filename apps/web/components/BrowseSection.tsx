"use client";

import Link from "next/link";
import { track, type ResultOrigin } from "@/lib/analytics";

export interface BrowseItem {
  href: string;
  name: string;
  /** "35 parts on this chip" — the count comes from the API's facets, the wording from the caller. */
  note: string;
  partId: string;
  partType: string;
}

// A crawlable index of links rendered by the server (the home page's ISR render),
// so every hub has a path from "/" in plain HTML. Client component only for the
// click tracking; it holds no state.
export default function BrowseSection({
  id,
  title,
  hint,
  items,
  origin,
}: {
  id: string;
  title: string;
  hint: string;
  items: BrowseItem[];
  origin: ResultOrigin;
}) {
  if (items.length === 0) return null;
  return (
    <section className="browse-section" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="panel-title">
        {title}
      </h2>
      <p className="panel-hint">{hint}</p>
      <ul className="browse-list">
        {items.map((item, index) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="browse-link"
              onClick={() =>
                track("result_click", { part_id: item.partId, part_type: item.partType, origin, position: index + 1 })
              }
            >
              <span className="browse-link-name">{item.name}</span>
              <span className="browse-link-note">{item.note}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
