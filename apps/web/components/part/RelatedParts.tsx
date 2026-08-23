"use client";

import Link from "next/link";
import type { PartDetail, PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { brandLabel } from "@/lib/brand";
import { typePlural } from "@/lib/format";

const TYPE_ORDER = ["board", "module", "soc"];

export default function RelatedParts({ part }: { part: PartDetail }) {
  if (part.related.length === 0) return <p className="muted">No other parts on this chip yet.</p>;

  const socName = part.chain.soc?.name ?? part.name;
  const groups = new Map<string, PartRecord[]>();
  for (const record of part.related) {
    const list = groups.get(record.type) ?? [];
    list.push(record);
    groups.set(record.type, list);
  }

  return (
    <>
      {TYPE_ORDER.filter((type) => groups.has(type)).map((type) => {
        const items = groups.get(type)!;
        return (
          <div key={type} className="related-group">
            <h3>
              {typePlural(type)} on {socName} ({items.length})
            </h3>
            <ul className="related-list">
              {items.map((record, index) => (
                <li key={record.id}>
                  <Link
                    href={`/parts/${encodeURIComponent(record.id)}`}
                    className="related-item"
                    onClick={() =>
                      track("result_click", { part_id: record.id, part_type: record.type, origin: "related", position: index + 1 })
                    }
                  >
                    <span>{record.name}</span>
                    <span className="related-item-brand">{brandLabel(record)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </>
  );
}
