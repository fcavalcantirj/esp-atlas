// The Flash Wizard panel's decisions (SPEC-wizard P2b), kept free of React and
// of the "@/" alias so plain `node --test` can pin them (see format.ts's header).
// FlashAction renders whatever flashPanelContent() returns and nothing else.
import type { Recipe } from "./api.ts";
import type { FlashHandoff, Manifest } from "./esp-web-tools.ts";
import { tierClaim } from "./flash-copy.ts";

export type FlashPhase =
  | { kind: "closed" }
  | { kind: "loading" }
  | { kind: "ready"; manifest: Manifest; manifestUrl: string }
  | { kind: "handoff"; reason: string }
  | { kind: "broken" };

export type FlashOpenPlan = { kind: "broken" } | { kind: "no_rail" } | { kind: "preflight"; manifestUrl: string };

/** The exact terminal equivalent of the in-browser rail (`esptool --chip … write-flash …`). */
export interface TerminalFallback {
  chip: string;
  offset: string;
  file: string;
  url: string;
}

export type FlashPanelContent =
  | { kind: "closed" }
  | { kind: "loading" }
  | { kind: "install"; manifest: Manifest; manifestUrl: string; terminal: TerminalFallback | null }
  | { kind: "handoff"; reason: string; flasherUrls: string[]; repoUrl: string | null }
  | { kind: "broken"; claim: string; explanation: string; docs: string[] };

export function installBlocked(recipe: Pick<Recipe, "status">): boolean {
  return false;
}

export function flashOpenPlan(recipe: Recipe, manifestUrl: string | null): FlashOpenPlan {
  return manifestUrl ? { kind: "preflight", manifestUrl } : { kind: "no_rail" };
}

/** Statically: does the record carry what the in-browser rail needs? The preflight remains the truth. */
export function inBrowserRail(recipe: Recipe, phaseKind: FlashPhase["kind"]): boolean {
  if (recipe.status === "broken" || phaseKind === "handoff") return false;
  const flash = recipe.flash;
  if (!flash) return false;
  if (flash.method === "release-bin") return Boolean(flash.bin_url);
  if (flash.method === "esp-web-tools") return Boolean(flash.manifest_url);
  return false;
}

// For the one failure the browser rail cannot get past: a chip whose CHIP magic
// the bundled esptool-js does not know (ESP32-C5 rev v1.2, 2026-09-01). Only for
// release-bin recipes — the offset and file are the recipe's own, so the command
// is a fact, not advice.
function terminalFallbackFor(recipe: Recipe): TerminalFallback | null {
  const flash = recipe.flash;
  if (flash?.method !== "release-bin" || !flash.bin_url) return null;
  return {
    chip: recipe.chip_family.replace("-", ""),
    offset: flash.offset ?? "0x0",
    file: flash.bin_url.split("/").pop() ?? "firmware.bin",
    url: flash.bin_url,
  };
}

export function flashPanelContent(recipe: Recipe, phase: FlashPhase, handoff: FlashHandoff, boardName: string): FlashPanelContent {
  switch (phase.kind) {
    case "closed":
    case "loading":
      return { kind: phase.kind };
    case "ready":
      return { kind: "install", manifest: phase.manifest, manifestUrl: phase.manifestUrl, terminal: terminalFallbackFor(recipe) };
    case "handoff":
      return { kind: "handoff", reason: phase.reason, flasherUrls: handoff.flasherUrls, repoUrl: handoff.repoUrl };
    case "broken":
      return { kind: "broken", claim: tierClaim(recipe.status, boardName), explanation: recipe.notes ?? "", docs: [] };
  }
}
