// The Verify rail's browser-only I/O (SPEC-verify.md "Rail A — VERIFY").
// Drives esptool-js's ESPLoader against the connected chip's ROM bootloader —
// detectChip() + read-only queries only, no stub upload, no flash write/erase.
// Deliberately thin and untested here: apps/web/lib/verify-board.ts's
// matchBoard() is the pure, unit-tested boundary this feeds.
import type { DetectedChip } from "@/lib/verify-board";

async function safe<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch {
    return null;
  }
}

function parsePsram(features: string[]): DetectedChip["psram"] {
  const hit = features.find((f) => /psram/i.test(f));
  if (!hit) return { present: false, sizeMb: null };
  const size = hit.match(/(\d+)\s*mb/i);
  return { present: true, sizeMb: size ? Number(size[1]) : null };
}

function parseFlashMb(flashSize: string): number | null {
  const mb = flashSize.match(/(\d+)\s*mb/i);
  if (mb) return Number(mb[1]);
  const kb = flashSize.match(/(\d+)\s*kb/i);
  return kb ? Number(kb[1]) / 1024 : null;
}

/**
 * Connects to `port` and reads chip identity, flash size, PSRAM and MAC.
 * Only `detectChip()` itself throws (no chip found / sync failed) — a
 * failure reading any one field afterwards degrades that field to
 * "not read" rather than aborting the whole detection.
 */
export async function detectChip(port: SerialPort): Promise<DetectedChip> {
  const { ESPLoader, Transport } = await import("esptool-js");
  const transport = new Transport(port, false);
  const loader = new ESPLoader({ transport, baudrate: 115200 });
  try {
    await loader.detectChip();
    const chipFamily = loader.chip.CHIP_NAME.toLowerCase();
    const features = await safe(() => loader.chip.getChipFeatures(loader));
    const mac = await safe(() => loader.chip.readMac(loader));
    const flashSizeText = await safe(() => loader.detectFlashSize());
    await safe(() => loader.after("hard_reset"));
    return {
      chipFamily,
      flashMb: flashSizeText ? parseFlashMb(flashSizeText) : null,
      psram: features ? parsePsram(features) : null,
      mac,
    };
  } finally {
    await transport.disconnect();
  }
}
