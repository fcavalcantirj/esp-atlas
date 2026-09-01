"use client";

import { useState } from "react";
import { resolveDownloadMode, type BootBoard } from "@/lib/troubleshooter";

// Shown below a Web Serial connect error on /debug (VerifyBoard's "Read my
// board" and the serial monitor both mount it): a short, numbered path back to
// a working connection instead of a dead-end error. Step 2's button sequence is
// board-specific and cited — resolveDownloadMode (unit-tested) decides what to
// show; this component only renders it and re-invokes the caller's own connect.
interface ConnectTroubleshooterProps {
  /** Boards that cite a download_mode (GET /api/boards/boot). */
  bootBoards: BootBoard[];
  /** Board id to prefill the picker with, when present in `bootBoards`. */
  defaultBoardId?: string;
  /** Re-invokes the caller's existing connect handler — no connect logic is duplicated here. */
  onRetry: () => void;
}

export default function ConnectTroubleshooter({ bootBoards, defaultBoardId, onRetry }: ConnectTroubleshooterProps) {
  const hasDefault = Boolean(defaultBoardId && bootBoards.some((b) => b.id === defaultBoardId));
  const [selectedId, setSelectedId] = useState(hasDefault ? defaultBoardId! : "");
  const selected = bootBoards.find((b) => b.id === selectedId) ?? null;
  const view = resolveDownloadMode(selected);

  return (
    <section className="verify-troubleshooter" aria-label="Connection troubleshooter">
      <h4 className="verify-troubleshooter-heading">Couldn’t connect? Walk through this</h4>
      <ol className="verify-troubleshooter-steps">
        <li>
          Use a <strong>data</strong> USB-C cable, not a power-only one — charge-only cables have no data lines, so the board never
          shows up in the port picker.
        </li>
        <li>
          Put the board in <strong>download / flash mode</strong>.
          <label className="verify-troubleshooter-picker">
            My board
            <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
              <option value="">Generic ESP32</option>
              {bootBoards.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          </label>
          <p className="verify-troubleshooter-mode">{view.steps}</p>
          {view.note && <p className="muted verify-troubleshooter-note">{view.note}</p>}
        </li>
        <li>
          Try the <strong>other USB-C port</strong> — some boards have two, and often only one is wired for flashing.
        </li>
        <li>
          Close any other serial app — Arduino IDE, or an <span className="mono">esp-idf</span> monitor — that may be holding the port
          open. Only one program can own a serial port at a time.
        </li>
      </ol>
      <button type="button" className="btn btn--sm" onClick={onRetry}>
        Try again
      </button>
    </section>
  );
}
