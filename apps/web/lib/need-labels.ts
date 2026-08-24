// How a wizard need / search filter reads to a human. Shared by the results
// header's active-filter chips and the example cards, so a given filter is
// worded the same wherever it is shown.
import type { SearchFilters, WizardNeeds } from "@/lib/api";
import type { LastQuery } from "@/lib/explorer";

const NEED_LABELS: Record<string, string> = {
  form: "form factor",
  budget: "budget",
  ieee802154: "smart-home mesh",
  usb_native: "native USB",
  radio: "Wi-Fi",
  band: "band",
  type: "type",
  protocol: "protocol",
  ble: "BLE",
  bt_classic: "BT Classic",
  q: "text",
  soc: "SoC",
  module: "module",
};

// The toggle sets psram_min to exactly this value; its chip reads as the
// friendly "can host a web server" claim instead of the raw MB threshold.
const HOSTING_LANE_PSRAM_MIN = 2;

export interface FilterChip {
  key: string;
  label: string;
}

/** One chip per set filter, in the order the object carries them. */
export function chipsFor(source: WizardNeeds | SearchFilters): FilterChip[] {
  return Object.entries(source as Record<string, unknown>)
    .filter(([, value]) => value !== undefined && value !== "" && value !== false && value !== null)
    .map(([key, value]) => {
      const label = NEED_LABELS[key] ?? key;
      if (value === true) return { key, label };
      if (key === "band") return { key, label: `${label}: ${String(value)} GHz` };
      if (key === "q") return { key, label: `"${String(value)}"` };
      if (key === "psram_min") {
        return value === HOSTING_LANE_PSRAM_MIN
          ? { key, label: "Can host a web server" }
          : { key, label: `PSRAM >= ${String(value)} MB` };
      }
      if (key === "flash_min") return { key, label: `Flash >= ${String(value)} MB` };
      return { key, label: `${label}: ${String(value)}` };
    });
}

export function activeChips(query: LastQuery | null): FilterChip[] {
  if (!query) return [];
  return chipsFor(query.kind === "wizard" ? query.needs : query.filters);
}

// Card wording is a different job from chip wording. A chip re-states the query
// the user already made ("Can host a web server"); an example card is asking
// them to make it, so its subtitle teaches the field underneath instead of
// echoing the card's own title. `type` is scoping, not a reason, so it drops
// out — it decides whether the count reads "boards" or "parts" (see countLabel).
function explainNeed(key: string, value: unknown): string | null {
  switch (key) {
    case "type":
      return null;
    case "psram_min":
      return `PSRAM >= ${String(value)} MB`;
    case "flash_min":
      return `flash >= ${String(value)} MB`;
    case "ieee802154":
      return "802.15.4 radio";
    case "usb_native":
      return "native USB";
    case "ble":
      return "Bluetooth LE";
    case "bt_classic":
      return "Bluetooth Classic";
    case "band":
      return `${String(value)} GHz band`;
    case "radio":
      return `${String(value)} or newer`;
    case "form":
      return `${String(value)} form factor`;
    case "budget":
      return `${String(value)} price tier`;
    default:
      return `${NEED_LABELS[key] ?? key}: ${String(value)}`;
  }
}

/** The real fields behind an example, for its card subtitle. */
export function explainNeeds(needs: WizardNeeds): string {
  return Object.entries(needs as Record<string, unknown>)
    .filter(([, value]) => value !== undefined && value !== "" && value !== false && value !== null)
    .map(([key, value]) => explainNeed(key, value))
    .filter((text): text is string => Boolean(text))
    .join(" · ");
}

/** "35 boards" when the query is scoped to boards, "35 parts" otherwise. */
export function countLabel(count: number, needs: WizardNeeds): string {
  const noun = needs.type ?? "part";
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}
