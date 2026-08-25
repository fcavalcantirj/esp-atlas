"use client";

// The grounded run_guide answer for a firmware intent (GET /run/{firmware_id}):
// what it needs, what it explicitly doesn't, and each board's own reasoned fit --
// an answer, not a keyword-search-lookalike. Every list here already reads as
// full sentences straight from esp_atlas_core.run_guide; this component only
// arranges them, it never rephrases or invents.
import Link from "next/link";
import TrackedLink from "@/components/TrackedLink";
import TrustTierBadge from "@/components/TrustTierBadge";
import { track } from "@/lib/analytics";
import type { RunGuideResponse } from "@/lib/api";
import { capabilityLabel, FIT_LABEL, runGuideBenefits } from "@/lib/format";

export default function RunGuideAnswer({ guide }: { guide: RunGuideResponse }) {
  const benefits = runGuideBenefits(guide.boards);

  return (
    <div className="run-guide">
      <div className="run-guide-header">
        {guide.firmware_name && <h2 className="run-guide-title">{guide.firmware_name}</h2>}
        <p className="run-guide-summary">{guide.summary}</p>
      </div>

      {guide.requires.length > 0 && (
        <div className="run-guide-section">
          <h3 className="run-guide-section-title">Needs</h3>
          <ul className="run-guide-req-list">
            {guide.requires.map((req) => (
              <li key={req.capability} className="run-guide-req">
                <span className="run-guide-req-cap">{capabilityLabel(req.capability)}</span>
                {req.why && <span className="run-guide-req-why"> — {req.why}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {guide.not_required.length > 0 && (
        <div className="run-guide-section run-guide-section--not-required">
          <h3 className="run-guide-section-title">Does not need</h3>
          <ul className="run-guide-req-list">
            {guide.not_required.map((entry) => (
              <li key={entry.capability} className="run-guide-req">
                <span className="run-guide-req-cap">{capabilityLabel(entry.capability)}</span>
                {entry.why && <span className="run-guide-req-why"> — {entry.why}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {benefits.length > 0 && (
        <div className="run-guide-section">
          <h3 className="run-guide-section-title">Benefits from</h3>
          <div className="chip-row">
            {benefits.map((benefit) => (
              <span key={benefit} className="chip">
                {benefit}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="run-guide-section">
        <h3 className="run-guide-section-title">Boards</h3>
        {guide.boards.length === 0 ? (
          <p className="muted">No boards recorded for this firmware yet.</p>
        ) : (
          <ul className="run-guide-boards">
            {guide.boards.map((board) => {
              const source = board.sources[0];
              return (
                <li key={board.board_id} className="run-guide-board">
                  <div className="run-guide-board-head">
                    <h4 className="run-guide-board-name">
                      <Link
                        href={`/parts/${encodeURIComponent(board.board_id)}`}
                        onClick={() => track("result_click", { part_id: board.board_id, part_type: "board", origin: "run_guide" })}
                      >
                        {board.board_name}
                      </Link>
                    </h4>
                    <span className={`fit-badge fit-badge--${board.fit}`}>{FIT_LABEL[board.fit] ?? board.fit}</span>
                  </div>
                  <p className="run-guide-board-meta">
                    {board.status && <TrustTierBadge status={board.status} />}
                    {board.chip_family && <span className="run-guide-board-chip">{board.chip_family}</span>}
                  </p>
                  {board.note && <p className="run-guide-board-note">{board.note}</p>}
                  {(board.reasons.length > 0 || board.particularities.length > 0) && (
                    <ul className="part-reasons" aria-label={`Why ${board.board_name}`}>
                      {board.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                      {board.particularities.map((fact) => (
                        <li key={fact}>{fact}</li>
                      ))}
                    </ul>
                  )}
                  {source && (
                    <p className="run-guide-board-source">
                      <TrackedLink href={source.url} linkType="source" extra={{ board: board.board_id }}>
                        source
                      </TrackedLink>
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {guide.excluded_boards && guide.excluded_boards.length > 0 && (
        <p className="run-guide-excluded">
          {guide.excluded_boards.length} board{guide.excluded_boards.length === 1 ? "" : "s"} excluded by the{" "}
          {guide.constraint?.chip ?? "requested"} constraint.
        </p>
      )}
    </div>
  );
}
