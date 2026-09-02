"use client";

import { useState, useSyncExternalStore } from "react";
import ConnectTroubleshooter from "@/components/verify/ConnectTroubleshooter";
import HelpTip from "@/components/HelpTip";
import SerialMonitor from "@/components/verify/SerialMonitor";
import VerdictBadge from "@/components/verify/VerdictBadge";
import { track } from "@/lib/analytics";
import type { BootBoard } from "@/lib/troubleshooter";
import { friendlySerialError } from "@/lib/serial-errors";
import { matchBoard, type BoardRecord, type DetectedChip, type VerifyResult } from "@/lib/verify-board";
import { detectChip, ESPTOOL_JS_VERSION, UnknownChipError } from "@/lib/verify-serial";
import { hex32 } from "@/lib/chip-identify";

// The debug rail (SPEC-verify.md): Rail A here, Rail B in SerialMonitor.
// Both are click-gated — nothing connects to the port until the human asks,
// same consent pattern as the Flash Wizard's FlashAction.

type Phase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "result"; result: VerifyResult; detected: DetectedChip }
  | { kind: "detected"; detected: DetectedChip }
  | { kind: "error"; message: string }
  // The chip connected and answered but nothing identified it (chip-identify.ts):
  // not a cable/boot-mode failure, so the troubleshooter is the wrong answer.
  // On a board page the human may proceed on the cited family; the port is
  // kept so the retry needs no second picker.
  | { kind: "unknown-chip"; message: string; magic: number | null; chipId: number | null; port: SerialPort };

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

/**
 * How the chip family was established, when that matters to the reader:
 * assumed (not a reading) or identified by chip-id while the magic value is
 * unknown to esptool-js's table — the exact case where the in-browser
 * flashers built on that table will refuse this chip.
 */
function provenanceNote(detected: DetectedChip): string | null {
  if (detected.identifiedBy === "assumed") {
    return `Chip family assumed from what esp-atlas cites, not read: the silicon answered CHIP magic ${hex32(
      detected.magic ?? null,
    )}, which esptool-js ${ESPTOOL_JS_VERSION} does not know. The other rows are real reads.`;
  }
  if (detected.identifiedBy === "chip-id" && detected.magicKnown === false) {
    return `Identified by chip-id (GET_SECURITY_INFO, id ${detected.chipId}); the CHIP magic ${hex32(
      detected.magic ?? null,
    )} is not in esptool-js ${ESPTOOL_JS_VERSION}'s table — a newer silicon revision. In-browser flashers built on that table (ESP Web Tools, web.esphome.io) will report "Unexpected CHIP magic value" for this chip; flash it from a terminal with esptool instead.`;
  }
  return null;
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
    await run(port, null);
  }

  // One detection pass. `assumeFamily` is only ever the record's cited SoC,
  // and only after the human clicked to proceed on it.
  async function run(port: SerialPort, assumeFamily: string | null) {
    setPhase({ kind: "connecting" });
    try {
      track("verify_connect", { board: boardName, assumed: assumeFamily ?? undefined });
      const detected = await detectChip(port, { assumeFamily });
      if (board) {
        const result = matchBoard(detected, board);
        track("verify_result", { board: boardName, overall: result.overall, identified_by: detected.identifiedBy });
        setPhase({ kind: "result", result, detected });
      } else {
        track("verify_result", { overall: "detected", identified_by: detected.identifiedBy });
        setPhase({ kind: "detected", detected });
      }
    } catch (err) {
      if (err instanceof UnknownChipError) {
        track("verify_unknown_chip", { board: boardName, magic: hex32(err.magic), chip_id: err.chipId ?? undefined });
        setPhase({ kind: "unknown-chip", message: err.message, magic: err.magic, chipId: err.chipId, port });
        return;
      }
      track("verify_error", { board: boardName });
      setPhase({
        kind: "error",
        message: friendlySerialError(
          err,
          err instanceof Error ? err.message : "Could not read the chip — check the connection and try again.",
        ),
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
              <ConnectTroubleshooter bootBoards={bootBoards} defaultBoardId={defaultBoardId} onRetry={() => void verify()} />
            </>
          )}

          {phase.kind === "unknown-chip" && (
            <div className="verify-unknown-chip">
              <p className="verify-error">{phase.message}</p>
              <p className="muted">
                The connection itself worked — this is an identification gap, not a cable or download-mode problem. Please report
                the values above to esptool-js (
                <a href="https://github.com/espressif/esptool-js/issues" rel="noopener noreferrer" target="_blank">
                  issues
                </a>
                ) so the next release knows this silicon.
              </p>
              {board?.soc ? (
                <>
                  <p>
                    esp-atlas cites this board as <span className="mono">{board.soc}</span>. Continue on that assumption? The chip-family row
                    will say <em>assumed</em>, never <em>match</em> — only flash size, PSRAM and MAC are real reads.
                  </p>
                  <button type="button" className="btn btn--sm" onClick={() => void run(phase.port, board.soc)}>
                    Continue as {board.soc}
                  </button>
                </>
              ) : (
                <p className="muted">
                  Open the board’s own esp-atlas page and verify from there — it knows which chip the board carries and can offer to
                  continue on that basis.
                </p>
              )}
            </div>
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
              {provenanceNote(phase.detected) && <p className="muted verify-provenance">{provenanceNote(phase.detected)}</p>}
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
              {provenanceNote(phase.detected) && <p className="muted verify-provenance">{provenanceNote(phase.detected)}</p>}
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
      <SerialMonitor />
    </section>
  );
}
