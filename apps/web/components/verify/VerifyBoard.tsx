"use client";

import { useState, useSyncExternalStore } from "react";
import ConnectTroubleshooter from "@/components/verify/ConnectTroubleshooter";
import HelpTip from "@/components/HelpTip";
import SerialMonitor from "@/components/verify/SerialMonitor";
import VerdictBadge from "@/components/verify/VerdictBadge";
import { track } from "@/lib/analytics";
import type { BootBoard } from "@/lib/troubleshooter";
import { matchBoard, type BoardRecord, type DetectedChip, type VerifyResult } from "@/lib/verify-board";
import { detectChip } from "@/lib/verify-serial";

// The debug rail (SPEC-verify.md): Rail A here, Rail B in SerialMonitor.
// Both are click-gated — nothing connects to the port until the human asks,
// same consent pattern as the Flash Wizard's FlashAction.

type Phase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "result"; result: VerifyResult }
  | { kind: "detected"; detected: DetectedChip }
  | { kind: "error"; message: string };

interface VerifyBoardProps {
  /** Board name for the cited-value comparison copy/analytics — omitted in detect-only mode. */
  boardName?: string;
  /** When omitted, this renders detect-only: chip readout only, no esp-atlas comparison (e.g. the standalone /debug page). */
  board?: BoardRecord;
  /** Boards with cited download-mode data (GET /api/boards/boot). When provided, a connect failure shows the troubleshooter. */
  bootBoards?: BootBoard[];
  /** Board id to prefill the troubleshooter's picker with. */
  defaultBoardId?: string;
}

function psramText(psram: DetectedChip["psram"]): string {
  if (psram === null) return "not read";
  if (!psram.present) return "no PSRAM";
  return psram.sizeMb !== null ? `${psram.sizeMb} MB` : "present (size unknown)";
}

// Server snapshot is always false so SSR/first-client-render stay identical;
// the real value only appears once the client subscribes, same pattern as
// HeaderControls' useMounted (avoids a setState-in-effect hydration hack).
function useSerialSupported(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => "serial" in navigator,
    () => false,
  );
}

export default function VerifyBoard({ boardName, board, bootBoards, defaultBoardId }: VerifyBoardProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const supported = useSerialSupported();

  async function verify() {
    if (!("serial" in navigator)) {
      setPhase({ kind: "error", message: "In-browser verify needs Web Serial: Chrome or Edge on a desktop." });
      return;
    }
    setPhase({ kind: "connecting" });
    let port: SerialPort;
    try {
      port = await navigator.serial.requestPort();
    } catch {
      setPhase({ kind: "idle" }); // user dismissed the picker — not an error
      return;
    }
    try {
      track("verify_connect", { board: boardName });
      const detected = await detectChip(port);
      if (board) {
        const result = matchBoard(detected, board);
        track("verify_result", { board: boardName, overall: result.overall });
        setPhase({ kind: "result", result });
      } else {
        track("verify_result", { overall: "detected" });
        setPhase({ kind: "detected", detected });
      }
    } catch (err) {
      track("verify_error", { board: boardName });
      setPhase({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not read the chip — check the connection and try again.",
      });
    }
  }

  const heading = board ? "Verify my board" : "Read my board";
  const intro = board
    ? `Reads the connected chip over USB and checks it against what esp-atlas cites for ${boardName} — over Web Serial, no backend, nothing leaves your browser.`
    : "Reads the connected chip over USB — chip family, flash size, PSRAM and MAC — over Web Serial, no backend, nothing leaves your browser.";

  return (
    <section className="verify-board" aria-labelledby="verify-board">
      <h2 id="verify-board">{heading}</h2>
      <p className="muted verify-intro">{intro}</p>

      {supported === false ? (
        <p className="verify-unsupported">
          In-browser verify needs Web Serial: Chrome or Edge on a desktop. Safari, Firefox and phones cannot do it.
        </p>
      ) : (
        <div className="verify-panel">
          <button type="button" className="btn btn--sm" onClick={() => void verify()} disabled={phase.kind === "connecting"}>
            {phase.kind === "connecting" ? "Connecting…" : heading}
          </button>

          {phase.kind === "error" && (
            <>
              <p className="verify-error">{phase.message}</p>
              {bootBoards && bootBoards.length > 0 && (
                <ConnectTroubleshooter bootBoards={bootBoards} defaultBoardId={defaultBoardId} onRetry={() => void verify()} />
              )}
            </>
          )}

          {phase.kind === "result" && (
            <>
              <table className="verify-table">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Chip says</th>
                    <th scope="col">esp-atlas cites</th>
                    <th scope="col">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {phase.result.fields.map((f) => (
                    <tr key={f.name}>
                      <th scope="row">{f.name}</th>
                      <td className="mono">{f.detected}</td>
                      <td className="mono">{f.cited}</td>
                      <td>
                        <VerdictBadge verdict={f.verdict} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {phase.result.mac && (
                <p className="muted verify-mac">
                  MAC address: <span className="mono">{phase.result.mac}</span> — informational only, esp-atlas cites no per-unit MAC to
                  check it against.
                </p>
              )}
            </>
          )}

          {phase.kind === "detected" && (
            <>
              <table className="verify-table">
                <thead>
                  <tr>
                    <th scope="col">Field</th>
                    <th scope="col">Chip says</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Chip family</th>
                    <td className="mono">{phase.detected.chipFamily ?? "not read"}</td>
                  </tr>
                  <tr>
                    <th scope="row">Flash size</th>
                    <td className="mono">{phase.detected.flashMb === null ? "not read" : `${phase.detected.flashMb} MB`}</td>
                  </tr>
                  <tr>
                    <th scope="row">PSRAM</th>
                    <td className="mono">{psramText(phase.detected.psram)}</td>
                  </tr>
                </tbody>
              </table>
              {phase.detected.mac && (
                <p className="muted verify-mac">
                  MAC address: <span className="mono">{phase.detected.mac}</span>
                </p>
              )}
            </>
          )}
        </div>
      )}

      <h3 className="verify-monitor-heading">
        Serial monitor
        <HelpTip
          field="serial_monitor"
          text="Streams whatever the firmware prints to UART, live, once the port is open — the plain 'watch it boot' debug loop."
        />
      </h3>
      <SerialMonitor bootBoards={bootBoards} defaultBoardId={defaultBoardId} />
    </section>
  );
}
