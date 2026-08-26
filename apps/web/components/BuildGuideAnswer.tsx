"use client";

// The grounded build_guide answer for an "unmapped" intent (POST /build): what
// the goal needs, the one firmware that fits (or honestly none), the real
// boards to run it on, and the honest add-on note -- the PRIMARY answer for a
// project goal, replacing the old "I can't narrow this" copy (SPEC-build-guide.md
// §6). Reuses RunGuideAnswer's .run-guide* classes verbatim: same box, same
// section rhythm -- no new visual system.
import Link from "next/link";
import { track } from "@/lib/analytics";
import type { BuildGuide } from "@/lib/api";

export default function BuildGuideAnswer({ guide }: { guide: BuildGuide }) {
  return (
    <div className="run-guide">
      <div className="run-guide-header">
        <h2 className="run-guide-title">To build {guide.goal}, you need</h2>
        {guide.needs.length > 0 && (
          <ul className="run-guide-req-list">
            {guide.needs.map((need) => (
              <li key={need} className="run-guide-req">
                {need}
              </li>
            ))}
          </ul>
        )}
      </div>

      {guide.firmware && (
        <div className="run-guide-section">
          <h3 className="run-guide-section-title">Firmware</h3>
          <p className="run-guide-summary">
            <Link
              href={`/firmware/${encodeURIComponent(guide.firmware.id)}`}
              onClick={() =>
                track("result_click", { part_id: guide.firmware!.id, part_type: "firmware", origin: "build_guide" })
              }
            >
              {guide.firmware.name}
            </Link>
            {" — "}
            {guide.firmware.why}
          </p>
        </div>
      )}

      {guide.boards.length > 0 && (
        <div className="run-guide-section">
          <h3 className="run-guide-section-title">Boards</h3>
          <ul className="run-guide-boards">
            {guide.boards.map((board) => (
              <li key={board.board_id} className="run-guide-board">
                <div className="run-guide-board-head">
                  <h4 className="run-guide-board-name">
                    <Link
                      href={`/parts/${encodeURIComponent(board.board_id)}`}
                      onClick={() =>
                        track("result_click", { part_id: board.board_id, part_type: "board", origin: "build_guide" })
                      }
                    >
                      {board.board_name}
                    </Link>
                  </h4>
                </div>
                <p className="run-guide-board-note">{board.why}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {guide.note && <p className="run-guide-excluded">{guide.note}</p>}
    </div>
  );
}
