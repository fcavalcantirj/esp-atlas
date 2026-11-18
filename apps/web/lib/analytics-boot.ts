// The analytics boot script, inlined in <body> before hydration (app/layout.tsx). It runs before gtag.js
// loads, so whatever it pushes onto dataLayer applies to every hit, including the automatic page_view.
//
// - Opt-out: localStorage `esp-atlas:analytics-disabled` = "1" disables collection entirely.
// - Internal traffic (2026-11-18): opening any page with `?internal=1` marks this browser as ours
//   (`?internal=0` clears it). While marked, `gtag('set', {internal: "1"})` tags every hit, so reports
//   (jr/feature_usage.py, the GA4 data filter) can exclude the maintainers' own use. Nothing else changes.
// - Consent Mode v2 (2026-11-18): the consent defaults (lib/consent.ts) are pushed first, so gtag.js sees them
//   before its config; a stored choice is replayed as an update.

import { consentBootScript } from "./consent.ts";

export const OPT_OUT_KEY = "esp-atlas:analytics-disabled";
export const INTERNAL_KEY = "esp-atlas:internal";

export function analyticsBootScript(gaId: string): string {
  const id = JSON.stringify(gaId);
  const optOut = JSON.stringify(OPT_OUT_KEY);
  const internal = JSON.stringify(INTERNAL_KEY);
  return (
    `window.__ESP_ATLAS_GA_ID=${id};window.dataLayer=window.dataLayer||[];` +
    consentBootScript() +
    `try{` +
    `if(localStorage.getItem(${optOut})==="1")window["ga-disable-"+${id}]=true;` +
    `var m=/[?&]internal=([01])(?:&|$)/.exec(location.search);` +
    `if(m){if(m[1]==="1")localStorage.setItem(${internal},"1");else localStorage.removeItem(${internal})}` +
    `if(localStorage.getItem(${internal})==="1")(function(){window.dataLayer.push(arguments)})("set",{internal:"1"})` +
    `}catch(e){}`
  );
}
