"use client";

import Link from "next/link";
import type { PartDetail, PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { typeLabel } from "@/lib/format";

// board → module → soc: the inheritance chain a part's radios come from.
export default function ChipChain({ part }: { part: PartDetail }) {
  const parents: { record: PartRecord; relation: "module" | "soc" }[] = [];
  if (part.chain.module) parents.push({ record: part.chain.module, relation: "module" });
  if (part.chain.soc) parents.push({ record: part.chain.soc, relation: "soc" });
  if (parents.length === 0) return null;

  return (
    <div className="chip-chain" aria-label="Built on">
      <span className="chip-chain-label">Built on</span>
      <span className="chip-chain-item chip-chain-item--current" aria-current="true">
        {part.name} <span className="badge">{typeLabel(part.type)}</span>
      </span>
      {parents.map(({ record, relation }) => (
        <span key={record.id} className="chip-chain">
          <span className="chip-chain-arrow" aria-hidden="true">
            →
          </span>
          <Link
            href={`/parts/${encodeURIComponent(record.id)}`}
            className="chip-chain-item"
            onClick={() => track("chain_click", { from_id: part.id, to_id: record.id, relation })}
          >
            {record.name} <span className="badge">{typeLabel(record.type)}</span>
          </Link>
        </span>
      ))}
    </div>
  );
}
