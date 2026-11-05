// Typed wrapper over @next/third-parties' sendGAEvent. Every user action on the
// site goes through track() with bounded, non-text parameters.
//
// GA4 custom parameters are not reportable until registered as custom dimensions
// / metrics in the GA4 admin (see apps/web/README.md for the list).
import { sendGAEvent } from "@next/third-parties/google";
import { GA_DEBUG } from "@/lib/site";
import { cleanEventParams, type EventParams } from "./analytics-params";
export type { EventParams } from "./analytics-params";

export type EventName =
  | "wizard_submit"
  | "wizard_results"
  | "wizard_empty"
  | "wizard_error"
  | "search_submit"
  | "search_results"
  | "search_empty"
  | "search_error"
  | "intent_parse"
  | "intent_submit"
  | "intent_result"
  | "intent_error"
  | "guide_result"
  | "guide_error"
  | "intent_clarifier_click"
  | "preset_click"
  | "example_click"
  | "relax_filter"
  | "result_click"
  | "part_view"
  | "chain_click"
  | "compare_add"
  | "compare_remove"
  | "compare_view"
  | "compare_filter"
  | "help_tip_open"
  | "advanced_filters_toggle"
  | "theme_change"
  | "font_size_change"
  | "outbound_click"
  | "api_error"
  | "not_found"
  | "shelf_see_all"
  // /firmware browse surface (SPEC-firmware-ordering.md / SPEC-firmware-popularity.md).
  | "firmware_sort"
  | "reveal_more"
  // Flash Wizard (SPEC-wizard P2b): panel opened, rail decided, consent, connect click.
  | "flash_open"
  | "flash_ready"
  | "flash_handoff"
  | "flash_consent"
  | "flash_connect"
  // Above-the-fold board-page CTA that jumps to #board-firmware (see BoardFlashCta) --
  // distinct from flash_open (fired per-recipe by FlashAction further down the page).
  | "board_flash_cta_click"
  // Verify rail (SPEC-verify.md): connect, result, and serial monitor use.
  | "verify_connect"
  | "verify_result"
  | "verify_error"
  | "verify_unknown_chip"
  | "monitor_connect"
  | "monitor_disconnect";

export type OutboundLinkType =
  | "source"
  | "github_edit"
  | "github_view"
  | "github_repo"
  | "contributing"
  | "agents"
  | "issues"
  | "new_issue"
  | "discussions"
  | "license"
  | "data_folder"
  | "llms_txt"
  | "api_docs"
  | "flash_handoff"
  | "roadmap";

export type ResultOrigin =
  | "wizard"
  | "search"
  | "related"
  | "compare"
  | "chain"
  | "browse"
  | "brand"
  | "popular_firmware"
  | "intent"
  | "build_guide";

export function track(name: EventName, params: EventParams = {}): void {
  const clean = cleanEventParams(params);
  if (GA_DEBUG) clean.debug_mode = true;
  if (typeof window === "undefined") return;
  const gaId = (window as Window & { __ESP_ATLAS_GA_ID?: string }).__ESP_ATLAS_GA_ID;
  if (!gaId) {
    if (process.env.NODE_ENV !== "production") console.debug("[analytics]", name, clean);
    return;
  }
  try {
    if (window.localStorage.getItem("esp-atlas:analytics-disabled") === "1") return;
  } catch {
    // Storage can be unavailable; the build-time switch still controls collection.
  }
  if (gaId === "G-66L7SDXKJZ" && window.location.hostname !== "esp-atlas.com") return;
  sendGAEvent("event", name, clean);
}

/** Sorted "k=v;k=v" string of the non-empty entries, so one query fits one GA4 dimension. */
export function serializeNeeds(obj: object): string {
  return Object.entries(obj as Record<string, unknown>)
    .filter(([, value]) => value !== undefined && value !== null && value !== "" && value !== false)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(";");
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** Convenience for external links: fires outbound_click, lets the navigation proceed. */
export function trackOutbound(linkType: OutboundLinkType, url: string, extra: EventParams = {}): void {
  track("outbound_click", { link_type: linkType, url, host: hostOf(url), ...extra });
}
