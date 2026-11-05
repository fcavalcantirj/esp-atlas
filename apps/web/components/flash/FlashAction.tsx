"use client";

import { useEffect, useId, useRef, useState } from "react";
import HelpTip from "@/components/HelpTip";
import TrackedLink from "@/components/TrackedLink";
import TrustTierBadge from "@/components/TrustTierBadge";
import type { Recipe } from "@/lib/api";
import { track } from "@/lib/analytics";
import { ensureEspWebTools, isManifest, manifestUrlFor, type FlashHandoff, type Manifest } from "@/lib/esp-web-tools";
import { recipeCaveat, tierClaim as tierClaimFor } from "@/lib/flash-copy";
import { flashOpenPlan, flashPanelContent, inBrowserRail, installBlocked, type FlashPhase } from "@/lib/flash-rail";
import { flashMethodLabel } from "@/lib/format";
import { hostOf } from "@/lib/analytics";
import { downloadModeView, type DownloadMode } from "@/lib/troubleshooter";

// The Flash Wizard's per-recipe action (SPEC-wizard "The Flash Wizard" + P2b).
// Opening the panel decides the rail: the manifest URL is preflighted and only a
// real manifest mounts <esp-web-install-button>; anything else — a 404 (the
// designed "no in-browser flash" signal), a non-release-bin method, a fetch or
// loader failure — becomes the guided handoff to the project's own tools.
// The consent checkbox gates the button's `activate` slot: a disabled button
// emits no click, so the tool's connect() cannot run until the human agrees.
// A recipe recorded as broken gets no rail at all — no preflight, no button, no
// terminal command, no flasher handoff — only its cited explanation (lib/flash-rail).

const DISCLAIMER =
  "esp-atlas asserts this board↔firmware link at the shown trust tier — it does not guarantee your specific unit or the current firmware version. Flashing can erase keys/config and can brick the device. At your own risk.";

interface FlashActionProps {
  recipe: Recipe;
  /** Human name of the other end of the edge (the firmware on a board page, the board on a firmware page). */
  targetName: string;
  boardName: string;
  firmwareName: string;
  handoff: FlashHandoff;
  /** The board's cited `usb.connector`, when the record has one. */
  usbConnector?: string | null;
  /** The board's cited `download_mode` (board page), for the plug-in hint. Absent -> generic BOOT line. */
  downloadMode?: DownloadMode | null;
}

function chips(manifest: Manifest): string {
  return Array.from(new Set(manifest.builds.map((b) => b.chipFamily))).join(" / ");
}

/** The manifest's version, unless the recipe recorded none (the generator then writes "unspecified"). */
function versionText(manifest: Manifest): string {
  return manifest.version && manifest.version !== "unspecified" ? ` ${manifest.version}` : "";
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
  const status = failure === "manifest_404" ? 404 : failure.startsWith("http_") ? Number(failure.slice(5)) : null;
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
  downloadMode = null,
}: FlashActionProps) {
  const [preflight, setPreflight] = useState<FlashPhase>({ kind: "closed" });
  const [consent, setConsent] = useState(false);
  const consentId = useId();
  const detailsRef = useRef<HTMLDetailsElement>(null);
  // Each open() gets a generation; a result from a superseded run is dropped.
  const generation = useRef(0);
  const method = recipe.flash?.method ?? null;
  const methodLabel = flashMethodLabel(method);
  const broken = installBlocked(recipe);
  // Everything below renders from this alone, never from the raw preflight: a
  // broken recipe maps every open phase — even a stale or late result — to its
  // cited explanation, with nothing installable.
  const phase = flashPanelContent(recipe, preflight, handoff, boardName);
  // The record's own claim until the preflight rules; a handoff result corrects
  // the pill, and a recipe recorded as broken never glows.
  const inBrowser = inBrowserRail(recipe, phase.kind);
  // Which rail: our generated manifest + streaming proxy, or the project's own manifest.
  const projectRail = method === "esp-web-tools";
  const tierClaim = tierClaimFor(recipe.status, boardName);
  // The record's own caveat (e.g. "a discovery lead, nothing upstream confirms this board"):
  // shown before any rail, so no flash path skips past it.
  const caveat = recipeCaveat(recipe);
  // The board's cited download-mode steps when known; otherwise the generic
  // BOOT line. The esp-web-install-button behavior is unaffected by this hint.
  const dmView = downloadModeView(downloadMode);
  const usbText = usbConnector ? ` (${usbConnector.toUpperCase()})` : "";

  async function open() {
    const gen = ++generation.current;
    const current = () => gen === generation.current;
    track("flash_open", { recipe_id: recipe.id, method });
    const plan = flashOpenPlan(recipe, manifestUrlFor(recipe));
    if (plan.kind === "broken") {
      setPreflight({ kind: "broken" });
      return;
    }
    if (plan.kind === "no_rail") {
      track("flash_handoff", { recipe_id: recipe.id, method, reason: "no_rail" });
      setPreflight({ kind: "handoff", reason: handoffReason(recipe, handoff, "no_rail") });
      return;
    }
    const { manifestUrl } = plan;
    setPreflight({ kind: "loading" });
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
          setPreflight({ kind: "ready", manifest: body, manifestUrl });
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
    setPreflight({ kind: "handoff", reason: handoffReason(recipe, handoff, failure) });
  }

  // A <details> toggled open before hydration never fires onToggle: catch up on mount.
  useEffect(() => {
    if (detailsRef.current?.open && preflight.kind === "closed") void open();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <details
      ref={detailsRef}
      className={"flash-action" + (inBrowser ? " flash-action--browser" : "")}
      onToggle={(event) => {
        if (event.currentTarget.open) {
          if (preflight.kind === "closed") void open();
        } else {
          generation.current++; // drop any preflight still in flight
          setPreflight({ kind: "closed" });
          setConsent(false);
        }
      }}
    >
      <summary className="flash-action-summary">
        <span className="flash-action-title">{broken ? `${targetName} — not installable` : `Flash ${targetName}`}</span>
        <span className="flash-action-tags">
          {!broken && (
            <span className="flash-action-tag">
              {inBrowser ? "in-browser" : phase.kind === "handoff" ? "guided handoff" : (methodLabel ?? "guided")}
            </span>
          )}
          {recipe.status === "known-good" && <span className="flash-action-tag flash-action-tag--tier">known-good</span>}
          {broken && <span className="flash-action-tag flash-action-tag--broken">broken</span>}
          {caveat && !broken && <span className="flash-action-tag flash-action-tag--caveat">read the caveat</span>}
        </span>
        {/* The tip must not toggle the drawer: stop the click before <summary> sees it. */}
        <span
          className="flash-action-help"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
          }}
        >
          <HelpTip
            field="flash_action"
            text={
              broken
                ? `esp-atlas records ${firmwareName} on ${boardName} as broken, so it offers no way to install it. Open this for the cited explanation and docs.`
                : inBrowser
                ? `Flashes ${firmwareName} onto ${boardName} straight from this page over USB — Chrome or Edge on a desktop, no install. The binary is the project's own release, streamed through esp-atlas; the flasher checks the chip before writing and asks before any full erase.`
                : `${firmwareName} is not flashed from this page: the project distributes it through its own flasher or M5Burner. Open this to get the cited links and the plug-in steps.`
            }
          />
        </span>
      </summary>

      <div className="flash-panel" aria-live="polite">
        <p className="flash-disclaimer">
          <TrustTierBadge status={recipe.status} />{" "}
          {phase.kind === "broken"
            ? `${phase.claim} esp-atlas offers no install for it — no in-browser flash, no terminal command, no flasher handoff.`
            : DISCLAIMER}
        </p>

        {caveat && (
          <p className="flash-caveat" role="note" aria-label="Caveat from this recipe">
            <strong>{broken ? "Why:" : "Caveat:"}</strong> {caveat}
          </p>
        )}

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
              Plug the board in over USB{usbText} and pick its port.{" "}
              {dmView.isGeneric
                ? "The flasher resets the chip itself; hold BOOT while connecting only if it fails to enter download mode."
                : dmView.steps}
            </p>
            {!dmView.isGeneric && dmView.note && <p className="muted flash-hint">{dmView.note}</p>}
            {phase.terminal && (
              <p className="muted flash-hint flash-fallback">
                If the flasher stops at <span className="mono">Unexpected CHIP magic value</span>, your silicon revision is newer than the
                browser flasher’s chip table (see <em>Verify my board</em> above) — the board is fine. Flash the same image from a
                terminal instead:{" "}
                <span className="mono">
                  esptool --chip {phase.terminal.chip} write-flash {phase.terminal.offset} {phase.terminal.file}
                </span>{" "}
                after downloading it from{" "}
                <TrackedLink href={phase.terminal.url} linkType="flash_handoff" extra={{ recipe_id: recipe.id, kind: "bin" }}>
                  {hostOf(phase.terminal.url)}
                </TrackedLink>
                .
              </p>
            )}
          </>
        )}

        {phase.kind === "handoff" && (
          <div className="flash-handoff">
            <p>{phase.reason}</p>
            {(phase.flasherUrls.length > 0 || phase.repoUrl) && (
              <ul className="flash-handoff-links">
                {phase.flasherUrls.map((url) => (
                  <li key={url}>
                    <TrackedLink href={url} linkType="flash_handoff" extra={{ recipe_id: recipe.id, kind: "flasher" }}>
                      Official flasher — {hostOf(url)}
                    </TrackedLink>
                  </li>
                ))}
                {phase.repoUrl && (
                  <li>
                    <TrackedLink href={phase.repoUrl} linkType="flash_handoff" extra={{ recipe_id: recipe.id, kind: "repo" }}>
                      Project repository — releases and instructions
                    </TrackedLink>
                  </li>
                )}
              </ul>
            )}
            <p className="muted flash-hint">
              Plug the board in over USB{usbText}; that flasher resets the chip itself.{" "}
              {dmView.isGeneric
                ? "Hold BOOT while connecting only if it fails to enter download mode."
                : dmView.steps}
            </p>
            {!dmView.isGeneric && dmView.note && <p className="muted flash-hint">{dmView.note}</p>}
          </div>
        )}

        {phase.kind === "broken" && (
          <div className="flash-broken" role="note" aria-label="Why this recipe is not installable">
            {/* The recipe's notes already show as the caveat above; this is the fallback when it has none. */}
            {!caveat && <p>{phase.explanation}</p>}
            {phase.docs.length > 0 && (
              <ul className="flash-handoff-links" aria-label="Cited docs">
                {phase.docs.map((url) => (
                  <li key={url}>
                    <TrackedLink href={url} linkType="source" extra={{ recipe_id: recipe.id, kind: "broken_doc" }}>
                      {hostOf(url)}
                    </TrackedLink>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
