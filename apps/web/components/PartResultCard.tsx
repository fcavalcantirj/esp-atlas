"use client";

import Link from "next/link";
import type { BoardReason, PartRecord, WizardRecord } from "@/lib/api";
import { track, type ResultOrigin } from "@/lib/analytics";
import { brandLabel } from "@/lib/brand";
import TrackedLink from "@/components/TrackedLink";
import TrustTierBadge from "@/components/TrustTierBadge";
import { PRICE_TIER_NOTE, priceTierShort, specChips, typeLabel } from "@/lib/format";

interface PartResultCardProps {
  part: PartRecord | WizardRecord;
  origin: ResultOrigin;
  position?: number;
  /** The recipe's own cited justification for this board, when the card
   * answers a firmware intent -- never invented, only what the data states. */
  boardReason?: BoardReason;
}

export default function PartResultCard({ part, origin, position, boardReason }: PartResultCardProps) {
  const wizardPart = "reasons" in part ? (part as WizardRecord) : null;
  const chips = specChips(part);
  const citedSource = boardReason?.sources[0];

  return (
    <li className="part-card">
      <div className="part-card-head">
        <h3 className="part-card-title">
          <Link
            href={`/parts/${encodeURIComponent(part.id)}`}
            onClick={() => track("result_click", { part_id: part.id, part_type: part.type, origin, position })}
          >
            {part.name}
          </Link>
        </h3>
        <p className="part-card-meta">
          <span className={`badge badge--${part.type}`}>{typeLabel(part.type)}</span>
          <span className="part-card-brand">{brandLabel(part)}</span>
          {part.price_tier && (
            <span className="price-pill" title={PRICE_TIER_NOTE}>
              {priceTierShort(part.price_tier)}
            </span>
          )}
        </p>
      </div>
      {chips.length > 0 && (
        <div className="spec-chips">
          {chips.map((chip) => (
            <span key={chip.label} className={`spec-chip${chip.on ? " spec-chip--on" : ""}`}>
              {chip.label}
            </span>
          ))}
        </div>
      )}
      {wizardPart && wizardPart.reasons.length > 0 && (
        <ul className="part-reasons" aria-label="Why it matches">
          {wizardPart.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {boardReason && (
        <ul className="part-reasons" aria-label="Why this board">
          <li>
            <TrustTierBadge status={boardReason.status} /> · {boardReason.chip_family} match
            {boardReason.reason ? ` · ${boardReason.reason}` : ""}
            {citedSource && (
              <>
                {" → "}
                <TrackedLink href={citedSource.url} linkType="source" extra={{ board: boardReason.board }}>
                  source
                </TrackedLink>
              </>
            )}
          </li>
        </ul>
      )}
    </li>
  );
}
