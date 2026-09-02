// The Verify rail's browser-only I/O (SPEC-verify.md "Rail A — VERIFY").
// Drives esptool-js's ESPLoader against the connected chip's ROM bootloader —
// read-only queries only, no stub upload, no flash write/erase.
//
// Identification is OURS, not esptool-js 0.6.1's `detectChip()`: that only
// consults the CHIP_DETECT_MAGIC table, and a newer silicon revision answers a
// value the table has never seen (ESP32-C5 rev v1.2 / ROM eco3 -> 0x30e1706f,
// 2026-09-01). We open+sync with `connect(..., detecting=false)`, then apply
// the order chip-identify.ts pins: GET_SECURITY_INFO chip-id first (what
// Python esptool does), the magic table second, a human-accepted assumption
// last. Upstream esptool-js merged the same chip-id path (#197, 2026-09-01);
// once a release ships it, `connect()`'s own detection could replace step 1 —
// keep the pure module's order and tests either way.
//
// Deliberately thin and untested here: chip-identify.ts (the order) and
// verify-board.ts (the matcher) are the pure, unit-tested boundaries this feeds.
import { identifyChip, parseSecurityInfoChipId, unknownChipMessage, type ChipDef, type ChipReadings } from "@/lib/chip-identify";
import type { DetectedChip } from "@/lib/verify-board";
import type { ROM } from "esptool-js";

/** Pinned in apps/web/package.json — named in user-facing messages so a bug report says which table failed. */
export const ESPTOOL_JS_VERSION = "0.6.1";

// ROM command the loader class does not expose as a constant in 0.6.1.
const ESP_GET_SECURITY_INFO = 0x14;
const SECURITY_INFO_LEN = 20;

// Chips whose ROM never answers GET_SECURITY_INFO (ESP8266, ESP32) or answers
// it without a chip id (ESP32-S2) — identified by magic only, as upstream does.
const MAGIC_ONLY = new Set(["esp8266", "esp32", "esp32-s2"]);

/** Thrown when the chip connected and answered but nothing identified it. */
export class UnknownChipError extends Error {
  readonly magic: number | null;
  readonly chipId: number | null;
  constructor(readings: ChipReadings) {
    super(unknownChipMessage(readings, ESPTOOL_JS_VERSION));
    this.name = "UnknownChipError";
    this.magic = readings.magic;
    this.chipId = readings.chipId;
  }
}

export interface DetectOptions {
  /** esp-atlas SoC id the human agreed to proceed on when nothing identifies the chip (board page only). */
  assumeFamily?: string | null;
}

async function safe<T>(fn: () => Promise<T>): Promise<T | null> {
  try {
    return await fn();
  } catch {
    return null;
  }
}

interface RomEntry {
  family: string;
  rom: ROM;
}

// esptool-js exports no ROM registry in 0.6.1 (upstream added ROM_LIST in
// #197); instantiate every target it ships and read the table off them, so the
// numbers come from the same version the loader runs — never retyped here.
async function loadRoms(): Promise<RomEntry[]> {
  const mods = await Promise.all([
    import("esptool-js/lib/targets/esp8266.js"),
    import("esptool-js/lib/targets/esp32.js"),
    import("esptool-js/lib/targets/esp32s2.js"),
    import("esptool-js/lib/targets/esp32s3.js"),
    import("esptool-js/lib/targets/esp32c2.js"),
    import("esptool-js/lib/targets/esp32c3.js"),
    import("esptool-js/lib/targets/esp32c5.js"),
    import("esptool-js/lib/targets/esp32c6.js"),
    import("esptool-js/lib/targets/esp32c61.js"),
    import("esptool-js/lib/targets/esp32h2.js"),
    import("esptool-js/lib/targets/esp32p4.js"),
  ]);
  const roms: ROM[] = [
    new mods[0].ESP8266ROM(),
    new mods[1].ESP32ROM(),
    new mods[2].ESP32S2ROM(),
    new mods[3].ESP32S3ROM(),
    new mods[4].ESP32C2ROM(),
    new mods[5].ESP32C3ROM(),
    new mods[6].ESP32C5ROM(),
    new mods[7].ESP32C6ROM(),
    new mods[8].ESP32C61ROM(),
    new mods[9].ESP32H2ROM(),
    new mods[10].ESP32P4ROM(),
  ];
  return roms.map((rom) => ({ family: rom.CHIP_NAME.toLowerCase(), rom }));
}

function chipDefs(roms: RomEntry[]): ChipDef[] {
  return roms.map(({ family, rom }) => {
    const r = rom as unknown as { IMAGE_CHIP_ID?: number; CHIP_DETECT_MAGIC_VALUE?: number[] };
    return {
      family,
      chipId: MAGIC_ONLY.has(family) || typeof r.IMAGE_CHIP_ID !== "number" ? null : r.IMAGE_CHIP_ID,
      magics: (r.CHIP_DETECT_MAGIC_VALUE ?? []).map((m) => m >>> 0),
    };
  });
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
 * Connects to `port`, identifies the chip (chip-id -> magic -> assumption) and
 * reads flash size, PSRAM and MAC. Throws `UnknownChipError` when the chip
 * answered but nothing identified it (the caller may retry with
 * `assumeFamily`); any other throw is a connection/sync failure. A failure
 * reading one field afterwards degrades that field to "not read" rather than
 * aborting the whole detection.
 */
export async function detectChip(port: SerialPort, opts: DetectOptions = {}): Promise<DetectedChip> {
  const { ESPLoader, Transport } = await import("esptool-js");
  const roms = await loadRoms();
  const transport = new Transport(port, false);
  const loader = new ESPLoader({ transport, baudrate: 115200 });
  try {
    // Open + sync with the ROM bootloader only; no magic detection inside.
    await loader.connect("default_reset", 7, false);
    const info = await safe(() => loader.checkCommand("get security info", ESP_GET_SECURITY_INFO, new Uint8Array(0), 0, SECURITY_INFO_LEN));
    const chipId = parseSecurityInfoChipId(info instanceof Uint8Array ? info : null);
    const magicRaw = await safe(() => loader.readReg(loader.CHIP_DETECT_MAGIC_REG_ADDR));
    const magic = magicRaw === null ? null : magicRaw >>> 0;
    const readings: ChipReadings = { chipId, magic };
    const id = identifyChip(readings, chipDefs(roms), opts.assumeFamily ?? null);
    if (!id) throw new UnknownChipError(readings);
    const rom = roms.find((r) => r.family === id.family)!.rom;
    loader.chip = rom;
    const addrMsb = (rom as unknown as { SPI_ADDR_REG_MSB?: boolean }).SPI_ADDR_REG_MSB;
    if (addrMsb !== undefined) loader.SPI_ADDR_REG_MSB = addrMsb;

    const features = await safe(() => loader.chip.getChipFeatures(loader));
    const mac = await safe(() => loader.chip.readMac(loader));
    const flashSizeText = await safe(() => loader.detectFlashSize());
    await safe(() => loader.after("hard_reset"));
    return {
      chipFamily: id.family,
      identifiedBy: id.by,
      magic: id.magic,
      chipId: id.chipId,
      magicKnown: id.magicKnown,
      flashMb: flashSizeText ? parseFlashMb(flashSizeText) : null,
      psram: features ? parsePsram(features) : null,
      mac,
    };
  } finally {
    await transport.disconnect();
  }
}
