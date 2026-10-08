"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import FirmwareMatchRow from "@/components/home/FirmwareMatchRow";
import IntentSearch from "@/components/home/IntentSearch";
import type { Firmware, PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { firmwareForChip } from "@/lib/board-compat";
import { hex32 } from "@/lib/chip-identify";
import { friendlySerialError } from "@/lib/serial-errors";
import type { DetectedChip } from "@/lib/verify-board";
import { detectChip, ESPTOOL_JS_VERSION, UnknownChipError } from "@/lib/verify-serial";

// The homepage's one primary action (SPEC-home rebuild §1): detect the
// connected chip over Web Serial -- reusing the exact detection order
// lib/chip-identify.ts/lib/verify-serial.ts pin, the same plumbing
// VerifyBoard drives on /debug and board pages -- then show only the
// firmware actually cited (lib/board-compat.ts) to run on it.

const MAX_HERO_MATCHES = 6;

type Phase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "detected"; detected: DetectedChip }
  | { kind: "error"; message: string }
  | { kind: "unknown-chip"; message: string; magic: number | null; chipId: number | null };

// Server snapshot is always false so SSR/first-client-render stay identical
// (same idiom as VerifyBoard's useSerialSupported / HeaderControls' useMounted).
function useSerialSupported(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => "serial" in navigator,
    () => false,
  );
}

function psramText(psram: DetectedChip["psram"]): string {
  if (psram === null) return "not read";
  if (!psram.present) return "no PSRAM";
  return psram.sizeMb !== null ? `${psram.sizeMb} MB` : "present (size unknown)";
}

export default function PlugToFlashHero({ firmware, parts }: { firmware: Firmware[]; parts: PartRecord[] }) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const supported = useSerialSupported();

  async function detect() {
    if (!("serial" in navigator)) {
      setPhase({ kind: "error", message: "In-browser detection needs Web Serial: Chrome or Edge on a desktop." });
      return;
    }
    setPhase({ kind: "connecting" });
    track("home_detect_click", {});
    let port: SerialPort;
    try {
      port = await navigator.serial.requestPort();
    } catch {
      setPhase({ kind: "idle" }); // user dismissed the picker -- not an error
      return;
    }
    try {
      const detected = await detectChip(port);
      track("home_detect_result", { chip_family: detected.chipFamily, identified_by: detected.identifiedBy });
      setPhase({ kind: "detected", detected });
    } catch (err) {
      if (err instanceof UnknownChipError) {
        track("home_detect_unknown_chip", { magic: hex32(err.magic), chip_id: err.chipId });
        setPhase({ kind: "unknown-chip", message: err.message, magic: err.magic, chipId: err.chipId });
        return;
      }
      track("home_detect_error", {});
      setPhase({
        kind: "error",
        message: friendlySerialError(
          err,
          err instanceof Error ? err.message : "Could not read the chip — check the connection and try again.",
        ),
      });
    }
  }

  const chipFamily = phase.kind === "detected" ? phase.detected.chipFamily : null;
  const matches = chipFamily ? firmwareForChip(firmware, chipFamily) : [];

  return (
    <section className="plug-hero" aria-labelledby="plug-hero-title">
      <p className="plug-hero-kicker mono">
        <span className="plug-hero-live" aria-hidden="true" /> every firmware verified &amp; cited
      </p>
      <h1 id="plug-hero-title" className="plug-hero-title">
        Plug your board in.
        <br />
        <em>Flash in seconds.</em>
      </h1>
      <p className="plug-hero-sub">
        esp-atlas reads your board over USB, shows only the firmware actually cited to run on it — and flashes it right
        here. No downloads, no guesswork.
      </p>

      <div className="plug-hero-actions">
        {supported === false ? (
          <p className="plug-hero-unsupported">
            In-browser detection needs Web Serial: Chrome or Edge on a desktop. Type what you want to build instead ↓
          </p>
        ) : (
          <button
            type="button"
            className="btn btn--primary plug-detect-btn"
            onClick={() => void detect()}
            disabled={phase.kind === "connecting"}
          >
            {phase.kind === "connecting" ? "Scanning USB…" : "⚡ Detect my board"}
          </button>
        )}
        <IntentSearch firmware={firmware} parts={parts} detectedChipFamily={chipFamily} />
      </div>
      <p className="plug-hero-hint mono">
        no board handy? <strong>type an intent</strong> — e.g. &ldquo;cardputer wifi scanner&rdquo;, &ldquo;mesh
        messaging&rdquo;, &ldquo;badusb&rdquo;
      </p>

      {phase.kind === "error" && (
        <div className="plug-detected plug-detected--error">
          <p className="plug-hero-unsupported">{phase.message}</p>
          <p className="muted">
            <Link href="/debug">Open the full connect troubleshooter →</Link>
          </p>
        </div>
      )}

      {phase.kind === "unknown-chip" && (
        <div className="plug-detected plug-detected--error">
          <p className="plug-hero-unsupported">{phase.message}</p>
          <p className="muted">
            The connection worked — esptool-js {ESPTOOL_JS_VERSION}&apos;s chip table just doesn&apos;t know this silicon
            revision yet. Report CHIP magic <span className="mono">{hex32(phase.magic)}</span> to{" "}
            <a href="https://github.com/espressif/esptool-js/issues" rel="noopener noreferrer" target="_blank">
              esptool-js
            </a>
            , or open the board&apos;s own page and verify from there.
          </p>
        </div>
      )}

      {phase.kind === "detected" && (
        <div className="plug-detected">
          <div className="plug-detected-head">
            <span className="plug-detected-ok" aria-hidden="true">
              ✓
            </span>
            <div>
              <p className="plug-detected-name">{phase.detected.chipFamily?.toUpperCase() ?? "Unknown chip"}</p>
              <p className="plug-detected-meta mono">
                detected over USB-serial
                {phase.detected.flashMb !== null && ` · ${phase.detected.flashMb} MB flash`}
                {phase.detected.psram?.present && ` · PSRAM ${psramText(phase.detected.psram)}`}
              </p>
            </div>
            <span className="plug-detected-count mono">{matches.length} firmware cited for this chip</span>
          </div>
          {matches.length === 0 ? (
            <p className="muted plug-detected-empty">
              Nothing in the atlas is cited to run on {phase.detected.chipFamily ?? "this chip"} yet — browse the whole
              catalog below, or <Link href="/wizard">open the spec wizard</Link>.
            </p>
          ) : (
            <ul className="match-list">
              {matches.slice(0, MAX_HERO_MATCHES).map((item, index) => (
                <FirmwareMatchRow
                  key={item.id}
                  firmware={item}
                  parts={parts}
                  origin="detect"
                  position={index + 1}
                  chipFamily={chipFamily}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
