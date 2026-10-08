// Honest chip-family compatibility for the home hero's "Detect my board" flow
// (SPEC-home rebuild §1: "runs on this board" MUST come from the firmware's
// own cited socs, never a match-everything heuristic). Web Serial only
// identifies the chip family (lib/verify-serial.ts), never the exact board
// model, so this matches at that same honest granularity.
import type { Firmware } from "@/lib/api";

export type Compat = "runs" | "no" | "unknown";

/**
 * How `firmware` relates to `chipFamily`: "runs" when its own cited `socs`
 * names the family, "no" when it cites other families but not this one, and
 * "unknown" when it cites no socs at all -- never fabricated either way.
 */
export function compatWithChip(firmware: Firmware, chipFamily: string): Compat {
  if (firmware.socs.length === 0) return "unknown";
  return firmware.socs.includes(chipFamily) ? "runs" : "no";
}

/**
 * Firmware cited to run on `chipFamily`, ranked by cited stars desc then
 * name A→Z -- the "detect my board" hero's result list.
 */
export function firmwareForChip(firmware: Firmware[], chipFamily: string): Firmware[] {
  return firmware
    .filter((item) => compatWithChip(item, chipFamily) === "runs")
    .slice()
    .sort((a, b) => (b.popularity?.stars ?? 0) - (a.popularity?.stars ?? 0) || a.name.localeCompare(b.name));
}
