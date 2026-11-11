import type { Firmware } from "@/lib/api";

/** The chip hub's "Firmware for <chip>" list (SPEC-serp-ctr.md §4): every
 * firmware whose own `socs` names the chip exactly, in the index's order.
 * Deterministic from GET /firmware -- no ranking, nothing inferred. */
export function firmwareForChip<T extends Pick<Firmware, "socs">>(firmware: T[], socId: string): T[] {
  return firmware.filter((fw) => fw.socs.includes(socId));
}
