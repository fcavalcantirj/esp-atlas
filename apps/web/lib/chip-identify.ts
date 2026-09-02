// Chip identification for the Verify rail (SPEC-verify.md "Detection"). Pure —
// no Web Serial, no esptool-js — so the identification ORDER is unit-testable:
//
//   1. chip-id  — the GET_SECURITY_INFO ROM command reports the silicon's
//                 IMAGE_CHIP_ID; independent of silicon revision. This is how
//                 Python esptool >= 4.9 identifies every chip since the ESP32-C3.
//   2. magic    — the classic CHIP_DETECT_MAGIC register (0x40001000), matched
//                 against esptool-js's per-chip table. That table is a snapshot:
//                 a newer ROM revision answers a value it has never seen.
//   3. assumed  — nothing matched, but the caller (a board page) knows what
//                 esp-atlas cites for this board and the human agreed to proceed
//                 on that assumption. Never silently: the result is labelled
//                 "assumed", and the matcher renders the chip-family verdict as
//                 unknown, not match.
//
// Origin: an ESP32-C5-DevKitC-1 with chip rev v1.2 (ROM eco3-20250704)
// answered magic 0x30e1706f, absent from esptool-js 0.6.1's C5 table
// [0x1101406f, 0x63e1406f, 0x5fd1406f]; Verify died with "Unexpected CHIP magic
// value" while Python esptool 5.3.0 identified the same chip via chip-id.
// Upstream esptool-js merged GET_SECURITY_INFO detection on 2026-09-01 (#197)
// but had not released it; verify-serial.ts carries step 1 until a release
// does, and this module stays the tested order either way.

/** One row of the identification table, built from esptool-js's ROM classes. */
export interface ChipDef {
  /** esp-atlas SoC id, e.g. "esp32-c5" (esptool-js CHIP_NAME lowercased). */
  family: string;
  /** IMAGE_CHIP_ID as reported by GET_SECURITY_INFO; null for chips that never answer it (ESP8266, ESP32, ESP32-S2). */
  chipId: number | null;
  /** CHIP_DETECT_MAGIC register values this chip is known to answer. */
  magics: number[];
}

export type IdentifiedBy = "chip-id" | "magic" | "assumed";

export interface ChipReadings {
  /** From GET_SECURITY_INFO, or null when the ROM does not answer it / the read failed. */
  chipId: number | null;
  /** The 32-bit CHIP_DETECT_MAGIC register, or null when the read failed. */
  magic: number | null;
}

export interface Identification extends ChipReadings {
  family: string;
  by: IdentifiedBy;
  /** True when `magic` is in the table — false means in-browser flashers built on the same table will not detect this chip. */
  magicKnown: boolean;
}

/**
 * Chip id from a GET_SECURITY_INFO response payload (status bytes already
 * stripped). Layout per esptool: flags[4] flash_crypt_cnt[1] key_purposes[7]
 * chip_id[4] api_version[4] = 20 bytes; the ESP32-S2 answers a 12-byte form
 * that carries no chip id. Little-endian, unsigned.
 */
export function parseSecurityInfoChipId(payload: Uint8Array | null | undefined): number | null {
  if (!payload || payload.length < 16) return null;
  return (payload[12] | (payload[13] << 8) | (payload[14] << 16) | (payload[15] << 24)) >>> 0;
}

export function familyFromChipId(chipId: number | null, defs: ChipDef[]): string | null {
  if (chipId === null) return null;
  const hit = defs.find((d) => d.chipId !== null && d.chipId === chipId);
  return hit ? hit.family : null;
}

export function familyFromMagic(magic: number | null, defs: ChipDef[]): string | null {
  if (magic === null) return null;
  const hit = defs.find((d) => d.magics.includes(magic >>> 0));
  return hit ? hit.family : null;
}

/**
 * Resolve the readings to a chip family, in the documented order. Returns null
 * when nothing identifies the chip and no (valid) assumption was offered — the
 * caller decides whether to ask the human for one.
 */
export function identifyChip(readings: ChipReadings, defs: ChipDef[], assumedFamily: string | null = null): Identification | null {
  const magicKnown = familyFromMagic(readings.magic, defs) !== null;
  const byId = familyFromChipId(readings.chipId, defs);
  if (byId) return { ...readings, family: byId, by: "chip-id", magicKnown };
  const byMagic = familyFromMagic(readings.magic, defs);
  if (byMagic) return { ...readings, family: byMagic, by: "magic", magicKnown };
  if (assumedFamily && defs.some((d) => d.family === assumedFamily)) {
    return { ...readings, family: assumedFamily, by: "assumed", magicKnown };
  }
  return null;
}

export function hex32(value: number | null): string {
  return value === null ? "not read" : `0x${(value >>> 0).toString(16).padStart(8, "0")}`;
}

/** Plain-language explanation for a chip nothing identified. */
export function unknownChipMessage(readings: ChipReadings, toolVersion: string): string {
  const chipId = readings.chipId === null ? "not reported" : String(readings.chipId);
  return (
    `The chip connected and answered, but nothing identified it: CHIP magic ${hex32(readings.magic)}, chip-id ${chipId}. ` +
    `That magic value is not in esptool-js ${toolVersion}'s table — usually a silicon revision newer than the browser tools know.`
  );
}
