"use client";

import { useState } from "react";
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
  handoff: FlashHandoff;
  /** The board's cited `usb.connector`, when the record has one. */
  usbConnector?: string | null;
}

function handoffReason(recipe: Recipe, handoff: FlashHandoff, status: number | null): string {
  const method = recipe.flash?.method;
  if (method === "m5burner") return "This firmware is distributed through M5Burner, M5Stack's desktop flasher — not flashable from a browser.";
  if (method === "web-flasher")
    return handoff.flasherUrls.length > 0
      ? "This project ships its own web flasher; use it directly."
      : "This project ships its own flasher, which this recipe does not cite yet — start from the repository.";
  if (method === "release-bin" && status === 404) return "No verified binary is recorded for this recipe yet, so there is no in-browser flash. Use the project's own tools.";
  if (method === "esp-web-tools" && !recipe.flash?.manifest_url) return "This project publishes ESP Web Tools manifests, but this recipe does not cite one yet.";
  if (status !== null) return `The flash manifest could not be fetched (HTTP ${status}). Use the project's own tools.`;
  return "The in-browser flasher could not start here. Use the project's own tools.";
}

export default function FlashAction({ recipe, targetName, handoff, usbConnector = null }: FlashActionProps) {
  const [phase, setPhase] = useState<Phase>({ kind: "closed" });
  const [consent, setConsent] = useState(false);
  const method = recipe.flash?.method ?? null;
  const methodLabel = flashMethodLabel(method);

  async function open() {
    track("flash_open", { recipe_id: recipe.id, method });
    const manifestUrl = manifestUrlFor(recipe);
    if (!manifestUrl) {
      const reason = handoffReason(recipe, handoff, null);
      track("flash_handoff", { recipe_id: recipe.id, method, reason: "no_rail" });
      setPhase({ kind: "handoff", reason });
      return;
    }
    setPhase({ kind: "loading" });
    let status: number | null = null;
    try {
      const [, res] = await Promise.all([ensureEspWebTools(), fetch(manifestUrl)]);
      status = res.status;
      const body: unknown = res.ok ? await res.json() : null;
      if (res.ok && isManifest(body)) {
        track("flash_ready", { recipe_id: recipe.id, chip: body.builds.map((b) => b.chipFamily).join(","), version: body.version });
        setPhase({ kind: "ready", manifest: body, manifestUrl });
        return;
      }
    } catch {
      // loader or network failure — fall through to the handoff
    }
    track("flash_handoff", { recipe_id: recipe.id, method, reason: status === 404 ? "manifest_404" : status ? `http_${status}` : "load_failed" });
    setPhase({ kind: "handoff", reason: handoffReason(recipe, handoff, status) });
  }

  return (
    <details
      className="flash-action"
      onToggle={(event) => {
        if (event.currentTarget.open) {
          if (phase.kind === "closed") void open();
        } else {
          setPhase({ kind: "closed" });
          setConsent(false);
        }
      }}
    >
      <summary className="flash-action-summary">
        <span>Flash {targetName}</span>
        {methodLabel && <span className="flash-action-method">{methodLabel}</span>}
      </summary>

      <div className="flash-panel">
        <p className="flash-disclaimer">
          <TrustTierBadge status={recipe.status} /> {DISCLAIMER}
        </p>

        {phase.kind === "loading" && <p className="muted mono">Checking for an in-browser flash…</p>}

        {phase.kind === "ready" && (
          <>
            <p className="flash-facts mono">
              {phase.manifest.name} · {phase.manifest.version} · {phase.manifest.builds.map((b) => b.chipFamily).join(" / ")}
              {phase.manifest.new_install_prompt_erase ? " · asks before erasing" : ""}
            </p>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => {
                  setConsent(e.target.checked);
                  track("flash_consent", { recipe_id: recipe.id, checked: e.target.checked });
                }}
              />
              <span className="checkbox-text">I understand — enable the flash button</span>
            </label>
            <esp-web-install-button manifest={phase.manifestUrl}>
              <button
                slot="activate"
                type="button"
                className="btn btn--primary"
                disabled={!consent}
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
