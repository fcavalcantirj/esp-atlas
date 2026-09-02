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
  /** Cited first-flash gotchas (board.md `first_flash_notes`), e.g. a power jumper that must be fitted. */
  first_flash_notes?: string[] | null;
}

/**
 * The board's cited first-flash gotchas, or [] — blank entries dropped. The
 * 2026-09-01 origin: an ESP32-C5-DevKitC-1 shipped without its J5
 * current-measurement jumper, so the USB bridge enumerated, the power LED lit,
 * and the chip itself was unpowered — nothing in the cable/driver/download-mode
 * steps could have found it. Only the board's own record can say so.
 */
export function firstFlashNotes(board: BootBoard | null | undefined): string[] {
  const notes = board?.first_flash_notes;
  if (!Array.isArray(notes)) return [];
  return notes.filter((n): n is string => typeof n === "string" && n.trim() !== "").map((n) => n.trim());
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
 * Resolve the download-mode instructions to show for a bare `download_mode`
 * record (from a board's frontmatter or GET /api/boards/boot).
 *
 * No record -> the generic ESP32 sequence. An 'auto' board needs no buttons at
 * all. A 'manual' board shows its cited `steps`, falling back to the generic
 * sequence only if the record somehow carries none.
 */
export function downloadModeView(dm: DownloadMode | null | undefined): DownloadModeView {
  if (!dm) {
    return { steps: GENERIC_DOWNLOAD_STEPS, note: null, isGeneric: true };
  }
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

/**
 * Resolve the download-mode instructions to show for a selected board.
 * Thin wrapper over {@link downloadModeView} for the troubleshooter picker.
 */
export function resolveDownloadMode(board: BootBoard | null | undefined): DownloadModeView {
  return downloadModeView(board?.download_mode);
}
