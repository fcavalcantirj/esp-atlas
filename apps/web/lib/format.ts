// Display-only formatting of record fields. No decisions, no ranking — just labels.
import type { Firmware, PartRecord, RunGuideBoard } from "@/lib/api";
// Relative (not "@/") because this file must stay importable by plain
// `node --test` (see format.test.ts's header comment) -- the "@/" alias only
// resolves under Next's bundler.
import { SITE_NAME } from "./site.ts";

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

/** Display label for a recipe's distribution method; the flash affordance itself is components/flash/FlashAction. */
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

/** "Runs on N boards" card glance (SPEC-firmware-ordering.md §4.A/§5) -- null
 * below 1 so an un-recipe'd firmware renders nothing rather than "0 boards". */
export function boardsLabel(boards: number | null | undefined): string | null {
  if (!boards || boards < 1) return null;
  return `Runs on ${boards} board${boards === 1 ? "" : "s"}`;
}

// Google truncates SERP titles/descriptions mid-word around these lengths
// (SPEC-serp-ctr.md); every meta builder below enforces them itself so a
// long record name or summary can never blow the snippet budget.
const TITLE_MAX = 60;
const DESCRIPTION_MAX = 155;

/** Shortens `text` to fit `maxLen`, cutting at the last word boundary and
 * appending "…" -- never mid-word. No-op when it already fits. */
function truncateAtWord(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  const sliced = text.slice(0, maxLen - 1);
  const lastSpace = sliced.lastIndexOf(" ");
  return `${(lastSpace > 0 ? sliced.slice(0, lastSpace) : sliced).trimEnd()}…`;
}

/** "esp32-s3" -> "ESP32-S3": the SoC id's own casing, not a fabricated label. */
function socDisplay(soc: string): string {
  return soc.toUpperCase();
}

/**
 * Combines an entity name with a benefit clause into a title under
 * `TITLE_MAX` chars, leading with the name (the exact string people search)
 * as SPEC-serp-ctr.md requires. When the pair overflows, the name is
 * shortened at a word boundary rather than the benefit -- the benefit is
 * what carries the click-through lever (device/spec + intent).
 */
function buildMetaTitle(name: string, benefit: string): string {
  const full = `${name} — ${benefit}`;
  if (full.length <= TITLE_MAX) return full;
  const suffix = ` — ${benefit}`;
  return `${truncateAtWord(name, TITLE_MAX - suffix.length)}${suffix}`;
}

/**
 * SERP title for a firmware: leads with its exact name, then the strongest
 * flash/install benefit its own record can prove -- the boards it's
 * verified to run on when that count exists, else the SoCs it targets,
 * else a bare flash-guide fallback. Cite-or-omit: never states a board
 * count or SoC the record doesn't carry.
 *
 * A non-empty `seo_title` (data/firmware/<id>/firmware.md, opt-in per record)
 * overrides the formula outright -- already shaped "name — benefit" by the
 * author, so an overflow is shortened with the same word-boundary truncation
 * buildMetaTitle falls back to for its own name clause, applied here to the
 * whole override string instead. Absent/empty seo_title falls straight
 * through to the formula below, byte-identical to before it existed.
 */
export function firmwareMetaTitle(firmware: Pick<Firmware, "name" | "socs" | "boards" | "seo_title">): string {
  if (firmware.seo_title) {
    return truncateAtWord(firmware.seo_title, TITLE_MAX);
  }
  const socsLabel = firmware.socs.length > 0 ? firmware.socs.map(socDisplay).join("/") : null;
  const boards = firmware.boards ?? 0;

  const benefits = [
    boards > 0 && socsLabel ? `flash guide for ${socsLabel}, ${boards} board${boards === 1 ? "" : "s"}` : null,
    boards > 0 ? `flash guide, ${boards} board${boards === 1 ? "" : "s"}` : null,
    socsLabel ? `flash guide for ${socsLabel}` : null,
    "flash guide",
  ].filter((benefit): benefit is string => benefit !== null);

  for (const benefit of benefits) {
    const full = `${firmware.name} — ${benefit}`;
    if (full.length <= TITLE_MAX) return full;
  }
  // Every benefit still overflows even alongside the full name: keep the
  // shortest (last) one and shorten the name instead.
  return buildMetaTitle(firmware.name, benefits[benefits.length - 1]);
}

/**
 * Meta/JSON-LD description for a firmware: its Groq-grounded one-liner
 * (`summary`) when the enrichment pipeline has produced one, else a
 * category/socs/boards template that leads with the flash intent users
 * actually search for. Shared by the firmware page's generateMetadata and
 * structured-data.ts's SoftwareApplication node so the two never drift.
 * Cite-or-omit: the boards clause only appears when `boards` is a real,
 * positive count off the record.
 */
export function firmwareMetaDescription(
  firmware: Pick<Firmware, "name" | "category" | "socs" | "boards" | "summary">,
): string {
  if (firmware.summary) return truncateAtWord(firmware.summary, DESCRIPTION_MAX);
  const socsLabel = firmware.socs.length > 0 ? firmware.socs.map(socDisplay).join(", ") : "ESP32";
  const boards = firmware.boards ?? 0;
  const boardsClause = boards > 0 ? ` Verified to flash on ${boards} board${boards === 1 ? "" : "s"}.` : "";
  const base = `${firmware.name}: ${firmwareCategoryLabel(firmware.category)} firmware for ${socsLabel}.${boardsClause}`;
  return truncateAtWord(base, DESCRIPTION_MAX);
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

/** The concrete datasheet spec(s) worth leading a SERP snippet with, in the
 * order a shopper would care about them. Wi-Fi/BLE pair when both are cited
 * (most SoCs/modules); otherwise the first other real capability the part
 * has, so a part with none of these renders no spec clause rather than a
 * fabricated one. */
function partKeySpecs(part: Pick<PartRecord, "wifi_standard" | "ble_version" | "ieee802154" | "ieee802154_protocols" | "usb_native" | "form_factor">): string[] {
  const specs: string[] = [];
  const wifi = wifiLabel(part.wifi_standard);
  if (wifi) specs.push(wifi);
  if (part.ble_version) specs.push(`BLE ${part.ble_version}`);
  if (specs.length === 0 && part.ieee802154) specs.push(protocolsLabel(part.ieee802154_protocols) ?? "802.15.4");
  if (specs.length === 0 && part.usb_native) specs.push("native USB");
  if (specs.length === 0 && part.form_factor) specs.push(part.form_factor);
  return specs;
}

/**
 * SERP title for a part: leads with its exact name, then the type plus the
 * concrete spec(s) that make it worth clicking (e.g. "Wi-Fi 6 + BLE 5.3 SoC
 * specs") instead of the generic "{type} specs". Falls back to the bare type
 * when the record carries none of the headline radio/USB/form-factor fields.
 *
 * `hasPinout` appends the exact word "pinout" searchers scan for (e.g. "lolin
 * s2 mini pinout") right after the name -- SPEC-serp-ctr.md's 0%-CTR gap for
 * rank 8-20 pinout queries. Cite-or-omit: only pass `true` when the record's
 * own frontmatter.images.pinout is non-empty (BoardImage.tsx's "Pinout"
 * figure); `false`/omitted keeps the title byte-identical to before this
 * param existed.
 */
export function partMetaTitle(
  part: Pick<PartRecord, "name" | "type" | "wifi_standard" | "ble_version" | "ieee802154" | "ieee802154_protocols" | "usb_native" | "form_factor">,
  hasPinout = false,
): string {
  const specs = partKeySpecs(part);
  const benefit = specs.length > 0 ? `${specs.join(" + ")} ${typeLabel(part.type)} specs` : `${typeLabel(part.type)} specs`;
  const name = hasPinout ? `${part.name} pinout` : part.name;
  return buildMetaTitle(name, benefit);
}

/**
 * Meta description for a part: its own first body sentence when the record
 * has prose, else a type/spec template -- same cite-or-omit + length rules
 * as firmwareMetaDescription. `body` is optional because PartRecord itself
 * carries no prose (only PartDetail does); a part with no body sentence
 * falls straight to the template.
 */
export function partMetaDescription(
  part: Pick<PartRecord, "name" | "type" | "wifi_standard" | "ble_version" | "ieee802154" | "ieee802154_protocols" | "usb_native" | "form_factor">,
  body?: string,
): string {
  const sentence = body ? firstSentence(body) : "";
  if (sentence) return truncateAtWord(sentence, DESCRIPTION_MAX);
  const specs = partKeySpecs(part);
  const specClause = specs.length > 0 ? ` — ${specs.join(" + ")}` : "";
  return truncateAtWord(`${part.name}: datasheet-verified ${typeLabel(part.type)} specs${specClause} on ${SITE_NAME}.`, DESCRIPTION_MAX);
}

// data/firmware/*/firmware.md `requires`/`not_required` capability vocab -> the
// human label the run-guide answer teaches with. Mirrors esp_atlas_core.run_guide
// _CAP_LABELS -- kept in sync by hand since the two apps don't share code.
const CAPABILITY_LABEL: Record<string, string> = {
  wifi: "2.4GHz Wi-Fi",
  ble: "Bluetooth LE",
  bt_classic: "Bluetooth Classic",
  badusb: "USB HID (native USB)",
  "native-usb": "native USB",
  lora: "LoRa radio",
  gps: "GPS",
  "sub-ghz": "Sub-GHz radio",
  "rfid-nfc": "RFID/NFC",
  nfc: "NFC",
  ir: "IR blaster/receiver",
  mesh: "802.15.4 mesh radio",
  ethernet: "Ethernet",
  display: "a display",
  storage: "storage",
  psram: "PSRAM",
};

export function capabilityLabel(capability: string): string {
  return CAPABILITY_LABEL[capability] ?? capability;
}

// run_guide's per-board fit (esp_atlas_core.run_guide._fit_for): hard
// requirements gate it, benefits refine fit once hardware is fully met.
export const RUN_GUIDE_FIT_ORDER = ["ideal", "works", "partial", "unconfirmed"] as const;

export const FIT_LABEL: Record<string, string> = {
  ideal: "Ideal fit",
  works: "Works, with a tradeoff",
  partial: "Partial fit",
  unconfirmed: "Fit unconfirmed",
};

const BENEFIT_REASON_RE = /^benefits from (.+?) -> /;

/** The distinct benefit capabilities named across a run-guide's boards
 * (esp_atlas_core.run_guide._benefit_reasons emits "benefits from <label> ->
 * ..." lines per board) -- read back out into one deduped chip row instead of
 * repeating them inside every board's own reasons list. */
export function runGuideBenefits(boards: RunGuideBoard[]): string[] {
  const labels = new Set<string>();
  for (const board of boards) {
    for (const reason of board.reasons) {
      const match = BENEFIT_REASON_RE.exec(reason);
      if (match) labels.add(match[1].replace(/^an? /, ""));
    }
  }
  return [...labels];
}

// data/firmware/*/firmware.md `readme_lang` -- the language a README was
// machine-translated from, named for the "machine-translated from X" marker.
const README_LANGUAGE_NAME: Record<string, string> = {
  ja: "Japanese",
  zh: "Chinese",
  ko: "Korean",
};

export function readmeLanguageName(code: string): string {
  return README_LANGUAGE_NAME[code] ?? code;
}

/** 94567 -> "94.6k", 1234 -> "1.2k", 999 -> "999" (exact below 1000).
 * SPEC-firmware-popularity.md §2. Trailing ".0" is trimmed (1000 -> "1k", not "1.0k"). */
export function compactCount(n: number): string {
  if (n < 1000) return String(n);
  const scaled = (n / 1000).toFixed(1);
  const trimmed = scaled.endsWith(".0") ? scaled.slice(0, -2) : scaled;
  return `${trimmed}k`;
}

export interface PopularityInput {
  stars?: number | null;
  forks?: number | null;
  as_of?: string | null;
}

export interface PopularityGlance {
  stars?: string;
  forks?: string;
  ariaLabel: string;
  title?: string;
}

/** SPEC-firmware-popularity.md §2: the compact "★ 94.6k · ⑂ 12.4k" card glance.
 * `ariaLabel` carries the full, unabbreviated counts; `title` carries the
 * `as_of` tooltip when cited. Null when neither metric is present -- the
 * caller must render nothing, never a "0" or an empty glyph. */
export function popularityGlance(popularity: PopularityInput | null | undefined): PopularityGlance | null {
  if (!popularity) return null;
  const labelParts: string[] = [];
  const glance: PopularityGlance = { ariaLabel: "" };
  if (popularity.stars != null) {
    glance.stars = compactCount(popularity.stars);
    labelParts.push(`${popularity.stars.toLocaleString("en-US")} GitHub stars`);
  }
  if (popularity.forks != null) {
    glance.forks = compactCount(popularity.forks);
    labelParts.push(`${popularity.forks.toLocaleString("en-US")} forks`);
  }
  if (labelParts.length === 0) return null;
  glance.ariaLabel = labelParts.join(", ");
  if (popularity.as_of) glance.title = `stars as of ${popularity.as_of}`;
  return glance;
}

export function firstSentence(text: string): string {
  const stripped = text.replace(/^#\s[^\n]*\n+/, "").replace(/\*\*/g, "").trim();
  const match = /^(.+?[.!?])(\s|$)/.exec(stripped.replace(/\s+/g, " "));
  return (match ? match[1] : stripped).slice(0, 200);
}
