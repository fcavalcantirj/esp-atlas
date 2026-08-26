// Typed wrapper over @next/third-parties' sendGAEvent. Every user action on the
// site goes through track() with the actual values the user chose, so GA4 can
// answer "how do people search?" — not just "how many page views".
//
// GA4 custom parameters are not reportable until registered as custom dimensions
// / metrics in the GA4 admin (see apps/web/README.md for the list).
import { sendGAEvent } from "@next/third-parties/google";
import { GA_DEBUG, GA_ID } from "@/lib/site";

export type EventName =
  | "wizard_submit"
  | "wizard_results"
  | "wizard_empty"
  | "search_submit"
  | "search_results"
  | "search_empty"
  | "intent_parse"
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
  // Flash Wizard (SPEC-wizard P2b): panel opened, rail decided, consent, connect click.
  | "flash_open"
  | "flash_ready"
  | "flash_handoff"
  | "flash_consent"
  | "flash_connect";

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

export type ResultOrigin = "wizard" | "search" | "related" | "compare" | "chain" | "browse" | "brand" | "intent";

type ParamValue = string | number | boolean | undefined | null;
export type EventParams = Record<string, ParamValue>;

const MAX_PARAM_LENGTH = 100; // GA4 truncates event parameter values past 100 chars

function cleanParams(params: EventParams): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    out[key] = typeof value === "string" ? value.slice(0, MAX_PARAM_LENGTH) : value;
  }
  return out;
}

export function track(name: EventName, params: EventParams = {}): void {
  const clean = cleanParams(params);
  if (GA_DEBUG) clean.debug_mode = true;
  if (!GA_ID) {
    if (process.env.NODE_ENV !== "production") console.debug("[analytics]", name, clean);
    return;
  }
  if (typeof window === "undefined") return;
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
