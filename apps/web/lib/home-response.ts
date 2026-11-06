// Validate the fields the answer components actually render before accepting a
// successful HTTP response. Malformed JSON must become visible error/fallback UI.
import type { BuildGuide, IntentParse, PartRecord, RunGuideResponse } from "./api.ts";

const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string";
const optionalText = (v: unknown) => v == null || text(v);
const strings = (v: unknown) => Array.isArray(v) && v.every(text);
const list = (v: unknown, valid: (row: Record<string, unknown>) => boolean) => Array.isArray(v) && v.every(row => record(row) && valid(row));
function requireResponse(valid: boolean): asserts valid {
  if (!valid) throw new Error("The API returned an unreadable answer. Please try again.");
}

export function assertIntentResponse(v: unknown): asserts v is IntentParse {
  requireResponse(record(v) && ["firmware", "filters", "unmapped", "unreadable"].includes(String(v.kind))
    && record(v.filters) && strings(v.understood) && strings(v.unmapped)
    && optionalText(v.firmware) && optionalText(v.firmware_name) && typeof v.cached === "boolean");
}

export function assertRunGuideResponse(v: unknown, firmwareId: string): asserts v is RunGuideResponse {
  const requirement = (r: Record<string, unknown>) => text(r.capability) && optionalText(r.why);
  requireResponse(record(v) && v.firmware === firmwareId && optionalText(v.firmware_name)
    && text(v.summary) && typeof v.grounded === "boolean"
    && list(v.requires, requirement) && list(v.not_required, requirement)
    && list(v.boards, b => text(b.board_id) && text(b.board_name) && text(b.fit)
      && strings(b.reasons) && strings(b.particularities) && optionalText(b.status)
      && optionalText(b.note) && optionalText(b.chip_family) && list(b.sources, s => text(s.url)))
    && (v.excluded_boards == null || Array.isArray(v.excluded_boards))
    && (v.constraint == null || (record(v.constraint) && text(v.constraint.chip))));
}

export function assertBuildGuideResponse(v: unknown): asserts v is BuildGuide {
  requireResponse(record(v) && text(v.goal) && strings(v.needs) && optionalText(v.note)
    && (v.firmware == null || (record(v.firmware) && text(v.firmware.id) && text(v.firmware.name) && text(v.firmware.why)))
    && list(v.boards, b => text(b.board_id) && text(b.board_name) && text(b.why)));
}

export function assertPartResults(v: unknown): asserts v is { results: PartRecord[] } {
  const stringFields = ["vendor_or_brand", "brand_name", "wifi_standard", "wifi_bands", "ble_version",
    "ieee802154_protocols", "form_factor", "price_tier", "soc_ref", "module_ref"];
  requireResponse(record(v) && list(v.results, part => text(part.id) && text(part.name) && text(part.type)
    && stringFields.every(field => optionalText(part[field]))
    && ["flash_mb", "psram_mb"].every(field => part[field] == null || typeof part[field] === "number")
    && ["bt_classic", "ieee802154", "usb_native"].every(field => part[field] == null || typeof part[field] === "boolean")
    && (!("reasons" in part) || strings(part.reasons))));
}
