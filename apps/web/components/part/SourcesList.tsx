"use client";

import TrackedLink from "@/components/TrackedLink";
import type { PartDetail } from "@/lib/api";
import { hostOf } from "@/lib/analytics";

export default function SourcesList({ part }: { part: PartDetail }) {
  if (part.sources.length === 0) return <p className="muted">No sources on record.</p>;
  return (
    <>
      <ul className="sources-list">
        {part.sources.map((source) => (
          <li key={`${source.field}-${source.url}`}>
            <span className="sources-field">{source.field === "*" ? "Whole record" : source.field}</span>
            <TrackedLink href={source.url} linkType="source" extra={{ part_id: part.id, field: source.field }}>
              {hostOf(source.url)}
            </TrackedLink>
            <span className="sources-verified">verified {source.verified}</span>
          </li>
        ))}
      </ul>
      <p className="sources-note">Every spec on this page cites an official datasheet or vendor page. Wrong? Fix it by PR.</p>
    </>
  );
}
