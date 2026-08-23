// Display-only formatting of record fields. No decisions, no ranking — just labels.
import type { PartRecord } from "@/lib/api";

export function typeLabel(type: string): string {
  switch (type) {
    case "soc":
      return "SoC";
    case "module":
      return "Module";
    case "board":
      return "Board";
    default:
      return type;
  }
}

export function typePlural(type: string): string {
  switch (type) {
    case "soc":
      return "SoCs";
    case "module":
      return "Modules";
    case "board":
      return "Boards";
    default:
      return `${type}s`;
  }
}

/** "wifi-6" -> "Wi-Fi 6" */
export function wifiLabel(standard: string | null | undefined): string | null {
  if (!standard) return null;
  const match = /^wifi-(\d+)$/.exec(standard);
  return match ? `Wi-Fi ${match[1]}` : standard;
}

/** "2.4,5" -> "2.4 / 5 GHz" */
export function bandsLabel(bands: string | null | undefined): string | null {
  if (!bands) return null;
  return `${bands.split(",").join(" / ")} GHz`;
}

/** "zigbee-3.0,thread-1.3,matter" -> "Zigbee 3.0, Thread 1.3, Matter" */
export function protocolsLabel(protocols: string | null | undefined): string | null {
  if (!protocols) return null;
  return protocols
    .split(",")
    .map((token) => {
      const [family, version] = token.split("-");
      const name = family.charAt(0).toUpperCase() + family.slice(1);
      return version ? `${name} ${version}` : name;
    })
    .join(", ");
}

export const PRICE_TIER_LABEL: Record<string, string> = {
  cheap: "≈ cheap (under ~$15)",
  medium: "≈ medium (~$15–50)",
  expensive: "≈ expensive ($50+)",
};

export const PRICE_TIER_NOTE =
  "Approximate, editorial street-price tier — not a datasheet-verified spec. Used only by the wizard's budget filter.";

// Trust tiers, most to least trusted (SPEC-wizard.md "the honesty layer").
export const RECIPE_TIER_ORDER = ["known-good", "reported", "unverified", "broken"] as const;

export const RECIPE_TIER_LABEL: Record<string, string> = {
  "known-good": "Known good",
  reported: "Reported",
  unverified: "Unverified",
  broken: "Broken",
};

const FLASH_METHOD_LABEL: Record<string, string> = {
  "esp-web-tools": "web-serial",
  "release-bin": "release .bin",
  m5burner: "M5Burner",
  "web-flasher": "web flasher",
};

/** Informational only — never a flash affordance (that's a later phase). */
export function flashMethodLabel(method: string | null | undefined): string | null {
  if (!method) return null;
  return FLASH_METHOD_LABEL[method] ?? method;
}

const FIRMWARE_CATEGORY_LABEL: Record<string, string> = {
  pentest: "Pentest",
  mesh: "Mesh",
  badusb: "BadUSB",
  display: "Display",
  home: "Home",
  multi: "Multi-purpose",
};

export function firmwareCategoryLabel(category: string): string {
  return FIRMWARE_CATEGORY_LABEL[category] ?? category;
}

export function priceTierShort(tier: string | null | undefined): string | null {
  return tier ? `~${tier}` : null;
}

/** [21, 17.8] -> "21 × 17.8 mm", [131.5, 105.5, 10] -> "131.5 × 105.5 × 10 mm" */
export function dimensionsLabel(dims: unknown): string | null {
  if (!Array.isArray(dims) || dims.length < 2 || !dims.every((d) => typeof d === "number")) return null;
  return `${dims.join(" × ")} mm`;
}

export function yesNo(value: boolean | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return value ? "yes" : "no";
}

/** One-line spec summary for cards and compare headers. */
export function specChips(part: PartRecord): { label: string; on?: boolean }[] {
  const chips: { label: string; on?: boolean }[] = [];
  const wifi = wifiLabel(part.wifi_standard);
  if (wifi) chips.push({ label: part.wifi_bands ? `${wifi} · ${bandsLabel(part.wifi_bands)}` : wifi });
  if (part.ble_version) chips.push({ label: `BLE ${part.ble_version}` });
  if (part.bt_classic) chips.push({ label: "BT Classic" });
  if (part.ieee802154) chips.push({ label: `802.15.4 · ${protocolsLabel(part.ieee802154_protocols) ?? "yes"}`, on: true });
  if (part.usb_native) chips.push({ label: "Native USB", on: true });
  if (part.form_factor) chips.push({ label: part.form_factor });
  return chips;
}

export function firstSentence(text: string): string {
  const stripped = text.replace(/^#\s[^\n]*\n+/, "").replace(/\*\*/g, "").trim();
  const match = /^(.+?[.!?])(\s|$)/.exec(stripped.replace(/\s+/g, " "));
  return (match ? match[1] : stripped).slice(0, 200);
}
