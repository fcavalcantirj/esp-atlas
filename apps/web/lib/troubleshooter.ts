// First-flash connect troubleshooter data + the pure step-2 resolver
// (SPEC-first-flash.md P0). Plain module, no browser globals, so the same
// download-mode logic the ConnectTroubleshooter renders is unit-testable under
// `node --test` — same split as verify-board.ts behind VerifyBoard.

/** Board Firmware-Download-mode record, straight from GET /api/boards/boot
 * (which reads each board's frontmatter `download_mode` / `usb_serial`). */
export interface DownloadMode {
  /** 'auto' — the USB-serial bridge toggles EN/IO0 itself. 'manual' — `steps` is the button sequence. */
  mode: "auto" | "manual" | string;
  steps?: string | null;
  note?: string | null;
}

export interface BootBoard {
  id: string;
  name: string;
  download_mode: DownloadMode;
  usb_serial?: string | null;
}

/** The generic ESP32 sequence shown when no specific board is picked. */
export const GENERIC_DOWNLOAD_STEPS = "Hold BOOT, tap RESET, then release BOOT";

/** What step 2 of the troubleshooter renders for the current selection. */
export interface DownloadModeView {
  /** The instruction line to show. */
  steps: string;
  /** Board-specific gotcha (e.g. which of two USB ports), or null. */
  note: string | null;
  /** True when this is the fallback generic sequence, not a board's cited steps. */
  isGeneric: boolean;
}

/**
 * Resolve the download-mode instructions to show for a selected board.
 *
 * No board (default option) -> the generic ESP32 sequence. An 'auto' board
 * needs no buttons at all. A 'manual' board shows its cited `steps`, falling
 * back to the generic sequence only if the record somehow carries none.
 */
export function resolveDownloadMode(board: BootBoard | null | undefined): DownloadModeView {
  if (!board || !board.download_mode) {
    return { steps: GENERIC_DOWNLOAD_STEPS, note: null, isGeneric: true };
  }
  const dm = board.download_mode;
  const note = dm.note && dm.note.trim() ? dm.note : null;
  if (dm.mode === "auto") {
    return {
      steps: "This board enters download mode automatically — the USB-serial bridge does it for you, so no button sequence is needed.",
      note,
      isGeneric: false,
    };
  }
  const steps = dm.steps && dm.steps.trim() ? dm.steps : GENERIC_DOWNLOAD_STEPS;
  return { steps, note, isGeneric: false };
}
