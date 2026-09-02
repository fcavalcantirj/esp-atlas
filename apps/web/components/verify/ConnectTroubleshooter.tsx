"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { firstFlashNotes, resolveDownloadMode, type BootBoard } from "@/lib/troubleshooter";

// Shown below a Web Serial connect error on /debug (VerifyBoard's "Read my
// board" and the serial monitor both mount it): a short, numbered path back to
// a working connection instead of a dead-end error. Step 2's button sequence is
// board-specific and cited — resolveDownloadMode (unit-tested) decides what to
// show; this component only renders it and re-invokes the caller's own connect.
//
// The panel ALWAYS renders on a connect error — even with zero board data it
// shows the generic ESP32 sequence. The board list may arrive empty when the
// server-side fetch was cold/unreachable, so we also fetch it client-side as a
// fallback to populate the picker with per-board cited steps.
interface ConnectTroubleshooterProps {
  /** Boards that cite a download_mode (GET /api/boards/boot). Optional — fetched client-side if absent. */
  bootBoards?: BootBoard[];
  /** Board id to prefill the picker with, when present. */
  defaultBoardId?: string;
  /** Re-invokes the caller's existing connect handler — no connect logic is duplicated here. */
  onRetry: () => void;
}

export default function ConnectTroubleshooter({ bootBoards = [], defaultBoardId, onRetry }: ConnectTroubleshooterProps) {
  const [boards, setBoards] = useState<BootBoard[]>(bootBoards);
  const [selectedId, setSelectedId] = useState(
    defaultBoardId && bootBoards.some((b) => b.id === defaultBoardId) ? defaultBoardId : "",
  );

  // Fallback fetch when the server-side list came back empty.
  useEffect(() => {
    if (boards.length > 0) return;
    let cancelled = false;
    fetch(`${API_BASE}/boards/boot`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => { if (!cancelled && Array.isArray(data)) setBoards(data as BootBoard[]); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [boards.length]);

  // Prefill the default board once it becomes available (from prop or fetch).
  useEffect(() => {
    if (!selectedId && defaultBoardId && boards.some((b) => b.id === defaultBoardId)) {
      setSelectedId(defaultBoardId);
    }
  }, [boards, defaultBoardId, selectedId]);

  const selected = boards.find((b) => b.id === selectedId) ?? null;
  const view = resolveDownloadMode(selected);
  const notes = firstFlashNotes(selected);

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
              {boards.map((b) => (
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
          Check the board’s <strong>power jumper</strong>. Many devkits carry a current-measurement header whose jumper must be fitted —
          without it the USB bridge still shows up and the power LED still lights, but the chip itself is unpowered and answers on no
          port. Pick your board above for its cited details.
          {notes.length > 0 && (
            <ul className="verify-troubleshooter-notes">
              {notes.map((note) => (
                <li key={note} className="muted verify-troubleshooter-note">
                  {note}
                </li>
              ))}
            </ul>
          )}
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
