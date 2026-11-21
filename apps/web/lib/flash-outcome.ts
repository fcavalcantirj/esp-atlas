// What happened in esp-web-tools' install dialog, read when it closes (2026-11-18).
//
// esp-web-tools 10.4.0 (pinned in lib/esp-web-tools.ts) dispatches no progress events; the only event is a
// bubbling, composed `closed` on <ewt-install-dialog> (fire-event.js; install-dialog.js:983). The dialog
// does keep the last FlashState it received in `_installState` (install-dialog.js:929) until it closes,
// so reading it at `closed` gives the real outcome: `finished` = written and verified by the flasher,
// `error`, or a stage the user closed during. Anything this version never produces reads as `unknown` —
// a version bump that changes the shape degrades to "unknown", never to a wrong "success".

export type FlashResult = "success" | "failed" | "aborted" | "not_started" | "unknown";
export type FlashOutcome = { result: FlashResult; stage: string; chip: string | undefined };

const IN_PROGRESS = new Set(["initializing", "preparing", "erasing", "writing"]);

type DialogLike = { localName?: string; manifestPath?: string; _installState?: unknown } | null | undefined;

export function isInstallDialogFor(el: DialogLike, manifestUrl: string): boolean {
  return !!el && el.localName === "ewt-install-dialog" && el.manifestPath === manifestUrl;
}

export function flashOutcome(el: DialogLike): FlashOutcome {
  const st = el?._installState;
  if (st === undefined || st === null) return { result: "not_started", stage: "none", chip: undefined };
  if (typeof st !== "object" || typeof (st as { state?: unknown }).state !== "string") {
    return { result: "unknown", stage: "unreadable", chip: undefined };
  }
  const { state, chipFamily } = st as { state: string; chipFamily?: unknown };
  const chip = typeof chipFamily === "string" ? chipFamily : undefined;
  if (state === "finished") return { result: "success", stage: state, chip };
  if (state === "error") return { result: "failed", stage: state, chip };
  if (IN_PROGRESS.has(state)) return { result: "aborted", stage: state, chip };
  return { result: "unknown", stage: state.slice(0, 40), chip };
}

/** Coarse elapsed time from "Connect and flash" to the dialog closing; never a raw duration. */
export function elapsedBucket(ms: number): string {
  if (ms < 15_000) return "lt_15s";
  if (ms < 60_000) return "15s_1m";
  if (ms < 300_000) return "1m_5m";
  return "gt_5m";
}
