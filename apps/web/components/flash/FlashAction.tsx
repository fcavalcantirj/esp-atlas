"use client";

import { useEffect, useId, useRef, useState } from "react";
import TrackedLink from "@/components/TrackedLink";
import TrustTierBadge from "@/components/TrustTierBadge";
import type { Recipe } from "@/lib/api";
import { track } from "@/lib/analytics";
import { ensureEspWebTools, isManifest, manifestUrlFor, type FlashHandoff, type Manifest } from "@/lib/esp-web-tools";
import { flashMethodLabel } from "@/lib/format";
import { hostOf } from "@/lib/analytics";

// The Flash Wizard's per-recipe action (SPEC-wizard "The Flash Wizard" + P2b).
// Opening the panel decides the rail: the manifest URL is preflighted and only a
// real manifest mounts <esp-web-install-button>; anything else — a 404 (the
// designed "no in-browser flash" signal), a non-release-bin method, a fetch or
// loader failure — becomes the guided handoff to the project's own tools.
// The consent checkbox gates the button's `activate` slot: a disabled button
// emits no click, so the tool's connect() cannot run until the human agrees.

const DISCLAIMER =
  "esp-atlas asserts this board↔firmware link at the shown trust tier — it does not guarantee your specific unit or the current firmware version. Flashing can erase keys/config and can brick the device. At your own risk.";

type Phase =
  | { kind: "closed" }
  | { kind: "loading" }
  | { kind: "ready"; manifest: Manifest; manifestUrl: string }
  | { kind: "handoff"; reason: string };

interface FlashActionProps {
  recipe: Recipe;
  /** Human name of the other end of the edge (the firmware on a board page, the board on a firmware page). */
  targetName: string;
  boardName: string;
  firmwareName: string;
  handoff: FlashHandoff;
  /** The board's cited `usb.connector`, when the record has one. */
  usbConnector?: string | null;
}

// What each trust tier actually asserts (SPEC-wizard "Trust tiers") — the
// panel says this in words so "validated" never means more than the record does.
const TIER_CLAIM: Record<string, (board: string) => string> = {
  "known-good": (board) => `Known-good on ${board} — listed by the maintainer, or verified on real hardware.`,
  reported: (board) => `Reported on ${board} — community-submitted and cited, not independently verified.`,
  unverified: (board) => `Unverified on ${board} — harvested from the project's build targets, no human citation yet.`,
  broken: (board) => `Broken on ${board} — known incompatible, or regressed at a version.`,
};

function chips(manifest: Manifest): string {
  return Array.from(new Set(manifest.builds.map((b) => b.chipFamily))).join(" / ");
}

/** The manifest's version, unless the recipe recorded none (the generator then writes "unspecified"). */
function versionText(manifest: Manifest): string {
  return manifest.version && manifest.version !== "unspecified" ? ` ${manifest.version}` : "";
}

/** Statically: does the record carry what the in-browser rail needs? The preflight remains the truth. */
function looksFlashableInBrowser(recipe: Recipe): boolean {
  const flash = recipe.flash;
  if (!flash) return false;
  if (flash.method === "release-bin") return Boolean(flash.bin_url);
  if (flash.method === "esp-web-tools") return Boolean(flash.manifest_url);
  return false;
}

const PREFLIGHT_TIMEOUT_MS = 10_000;
const LOADER_TIMEOUT_MS = 15_000;

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${what} timed out`)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

type PreflightFailure = "no_rail" | "manifest_404" | "manifest_invalid" | "load_failed" | `http_${number}`;

function handoffReason(recipe: Recipe, handoff: FlashHandoff, failure: PreflightFailure): string {
  const method = recipe.flash?.method;
  if (failure === "manifest_invalid")
    return "esp-atlas's flash manifest for this recipe did not validate — please report it. Use the project's own tools meanwhile.";
  if (method === "m5burner") return "This firmware is distributed through M5Burner, M5Stack's desktop flasher — not flashable from a browser.";
  if (method === "web-flasher") {
    if (!handoff.known) return "This project ships its own flasher, but its record could not be loaded right now — open the firmware page or retry.";
    return handoff.flasherUrls.length > 0
      ? "This project ships its own web flasher; use it directly."
      : "This project ships its own flasher, which this recipe does not cite yet — start from the repository.";
  }
  const status = failure.startsWith("http_") ? Number(failure.slice(5)) : null;
  if (method === "release-bin" && status === 404)
    return "esp-atlas has no in-browser manifest for this recipe — no verified binary is recorded, or the browser flasher does not support its chip. Use the project's own tools.";
  if (method === "esp-web-tools" && !recipe.flash?.manifest_url) return "This project publishes ESP Web Tools manifests, but this recipe does not cite one yet.";
  if (status !== null) return `The flash manifest could not be fetched (HTTP ${status}). Use the project's own tools.`;
  return "The in-browser flasher could not start here. Use the project's own tools.";
}

export default function FlashAction({
  recipe,
  targetName,
  boardName,
  firmwareName,
  handoff,
  usbConnector = null,
}: FlashActionProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "closed" });
  const [consent, setConsent] = useState(false);
  const consentId = useId();
  const detailsRef = useRef<HTMLDetailsElement>(null);
  // Each open() gets a generation; a result from a superseded run is dropped.
  const generation = useRef(0);
  const method = recipe.flash?.method ?? null;
  const methodLabel = flashMethodLabel(method);
  const broken = recipe.status === "broken";
  // The record's own claim until the preflight rules; a handoff result corrects
  // the pill, and a recipe recorded as broken never glows.
  const inBrowser = !broken && phase.kind !== "handoff" && looksFlashableInBrowser(recipe);
  // Which rail: our generated manifest + streaming proxy, or the project's own manifest.
  const projectRail = method === "esp-web-tools";
  const tierClaim = (TIER_CLAIM[recipe.status] ?? ((board) => `${recipe.status} on ${board}.`))(boardName);

  async function open() {
    const gen = ++generation.current;
    const current = () => gen === generation.current;
    track("flash_open", { recipe_id: recipe.id, method });
    const manifestUrl = manifestUrlFor(recipe);
    if (!manifestUrl) {
      track("flash_handoff", { recipe_id: recipe.id, method, reason: "no_rail" });
      setPhase({ kind: "handoff", reason: handoffReason(recipe, handoff, "no_rail") });
      return;
    }
    setPhase({ kind: "loading" });
    let failure: PreflightFailure = "load_failed";
    try {
      const [, res] = await Promise.all([
        withTimeout(ensureEspWebTools(), LOADER_TIMEOUT_MS, "esp-web-tools"),
        fetch(manifestUrl, { signal: AbortSignal.timeout(PREFLIGHT_TIMEOUT_MS) }),
      ]);
      if (res.ok) {
        let body: unknown = null;
        try {
          body = await res.json();
        } catch {
          body = null;
        }
        if (isManifest(body)) {
          if (!current()) return;
          track("flash_ready", { recipe_id: recipe.id, chip: body.builds.map((b) => b.chipFamily).join(","), version: body.version });
          setPhase({ kind: "ready", manifest: body, manifestUrl });
          return;
        }
        failure = "manifest_invalid";
      } else {
        failure = res.status === 404 ? "manifest_404" : `http_${res.status}`;
      }
    } catch {
      failure = "load_failed"; // loader, network, or timeout
    }
    if (!current()) return;
    track("flash_handoff", { recipe_id: recipe.id, method, reason: failure });
    setPhase({ kind: "handoff", reason: handoffReason(recipe, handoff, failure) });
  }

  // A <details> toggled open before hydration never fires onToggle: catch up on mount.
  useEffect(() => {
    if (detailsRef.current?.open && phase.kind === "closed") void open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <details
      ref={detailsRef}
      className={"flash-action" + (inBrowser ? " flash-action--browser" : "")}
      onToggle={(event) => {
        if (event.currentTarget.open) {
          if (phase.kind === "closed") void open();
        } else {
          generation.current++; // drop any preflight still in flight
          setPhase({ kind: "closed" });
          setConsent(false);
        }
      }}
    >
      <summary className="flash-action-summary">
        <span className="flash-action-title">Flash {targetName}</span>
        <span className="flash-action-tags">
          <span className="flash-action-tag">
            {inBrowser ? "in-browser" : phase.kind === "handoff" ? "guided handoff" : (methodLabel ?? "guided")}
          </span>
          {recipe.status === "known-good" && <span className="flash-action-tag flash-action-tag--tier">known-good</span>}
          {broken && <span className="flash-action-tag flash-action-tag--broken">broken</span>}
        </span>
      </summary>

      <div className="flash-panel" aria-live="polite">
        <p className="flash-disclaimer">
          <TrustTierBadge status={recipe.status} /> {DISCLAIMER}
        </p>

        {phase.kind === "loading" && <p className="muted mono">Checking for an in-browser flash…</p>}

        {phase.kind === "ready" && (
          <>
            <ul className="flash-checks" role="list" aria-label="What esp-atlas checked">
              <li>{tierClaim}</li>
              {projectRail ? (
                <li>
                  The project&apos;s own manifest offers builds for {chips(phase.manifest)}; the flasher reads the connected chip and
                  refuses to write if none matches.
                </li>
              ) : (
                <li>
                  Built for {chips(phase.manifest)} — the same chip family as {boardName} (CI checks this for every recipe); the flasher
                  re-reads the connected chip and refuses a mismatch before writing.
                </li>
              )}
              <li>
                {firmwareName}
                {versionText(phase.manifest)},{" "}
                {projectRail
                  ? "fetched from the project's own manifest — esp-atlas never touches the binary"
                  : "the project's own release binary, streamed through esp-atlas unmodified"}
                {phase.manifest.new_install_prompt_erase ? " — you are asked before any full-chip erase" : ""}.
              </li>
            </ul>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => {
                  setConsent(e.target.checked);
                  track("flash_consent", { recipe_id: recipe.id, checked: e.target.checked });
                }}
              />
              <span className="checkbox-text" id={consentId}>
                I understand — enable the flash button
              </span>
            </label>
            <esp-web-install-button manifest={phase.manifestUrl}>
              <button
                slot="activate"
                type="button"
                className="btn btn--primary btn--flash"
                disabled={!consent}
                aria-describedby={consentId}
                onClick={() => track("flash_connect", { recipe_id: recipe.id })}
              >
                Connect and flash
              </button>
              <span slot="unsupported" className="flash-slot-note">
                In-browser flashing needs Web Serial: Chrome or Edge on a desktop. Safari, Firefox and phones cannot do it.
              </span>
              <span slot="not-allowed" className="flash-slot-note">Web Serial only works on HTTPS pages (or localhost).</span>
            </esp-web-install-button>
            <p className="muted flash-hint">
              Plug the board in over USB{usbConnector ? ` (${usbConnector.toUpperCase()})` : ""} and pick its port. The flasher resets
              the chip itself; hold BOOT while connecting only if it fails to enter download mode.
            </p>
          </>
        )}

        {phase.kind === "handoff" && (
          <div className="flash-handoff">
            <p>{phase.reason}</p>
            {(handoff.flasherUrls.length > 0 || handoff.repoUrl) && (
              <ul className="flash-handoff-links">
                {handoff.flasherUrls.map((url) => (
                  <li key={url}>
                    <TrackedLink href={url} linkType="flash_handoff" extra={{ recipe_id: recipe.id, kind: "flasher" }}>
                      Official flasher — {hostOf(url)}
                    </TrackedLink>
                  </li>
                ))}
                {handoff.repoUrl && (
                  <li>
                    <TrackedLink href={handoff.repoUrl} linkType="flash_handoff" extra={{ recipe_id: recipe.id, kind: "repo" }}>
                      Project repository — releases and instructions
                    </TrackedLink>
                  </li>
                )}
              </ul>
            )}
            <p className="muted flash-hint">
              Plug the board in over USB{usbConnector ? ` (${usbConnector.toUpperCase()})` : ""}; that flasher resets the chip itself.
              Hold BOOT while connecting only if it fails to enter download mode.
            </p>
          </div>
        )}
      </div>
    </details>
  );
}
