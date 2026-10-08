// Capability facet counting for the firmware wall's filter rail (SPEC-home
// rebuild §3). Pure -- no fetch, no DOM -- lib/capability-facets.test.ts
// exercises it directly; the component only renders what this returns.
import type { Firmware } from "@/lib/api";

/** The 8 capability chips the design's filter rail watches. */
export const WALL_CAPABILITIES = ["wifi", "ble", "lora", "mesh", "badusb", "ir", "gps", "sub-ghz"];

export interface CapabilityFacet {
  value: string;
  count: number;
}

/**
 * Counts, over `firmware`, how many cite each of `capabilities` (in that
 * order) -- only non-empty facets are returned so the filter rail never
 * offers a chip with nothing behind it.
 */
export function countCapabilities(firmware: Firmware[], capabilities: string[] = WALL_CAPABILITIES): CapabilityFacet[] {
  return capabilities
    .map((value) => ({ value, count: firmware.filter((item) => item.capabilities.includes(value)).length }))
    .filter((facet) => facet.count > 0);
}
