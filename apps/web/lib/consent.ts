// Google Consent Mode v2 for the EEA, the UK and Switzerland (owner's choice, 2026-11-18): there, analytics
// cookies stay off until the visitor accepts; everywhere else analytics runs as before. Ads storage is denied
// everywhere because the site runs no ads. The defaults are pushed by the boot script (lib/analytics-boot.ts)
// before gtag.js loads; the banner (components/ConsentBanner.tsx) records the visitor's choice here.

export const CONSENT_KEY = "esp-atlas:consent";

/** EEA (27 EU members + Iceland, Liechtenstein, Norway), the United Kingdom and Switzerland. */
export const CONSENT_REGIONS: readonly string[] = [
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
  "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "IS", "LI", "NO", "GB", "CH",
];

export type ConsentChoice = "granted" | "denied";

/** Whether a visitor from `country` (ISO alpha-2, e.g. Vercel's x-vercel-ip-country) must be asked first.
 *  An unknown country is asked: wrongly asking costs one click, wrongly not asking is the legal risk. */
export function consentRequired(country: string | null | undefined): boolean {
  if (!country) return true;
  return CONSENT_REGIONS.includes(country.trim().toUpperCase());
}

export function parseStoredConsent(value: string | null | undefined): ConsentChoice | null {
  return value === "granted" || value === "denied" ? value : null;
}

export function bannerVisible(stored: ConsentChoice | null, inConsentRegion: boolean): boolean {
  return stored === null && inConsentRegion;
}

/** The consent part of the boot script: defaults first, then any stored choice as an update. */
export function consentBootScript(): string {
  const deniedAds = `ad_storage:"denied",ad_user_data:"denied",ad_personalization:"denied"`;
  const regions = JSON.stringify(CONSENT_REGIONS);
  return (
    `(function(){var g=function(){window.dataLayer.push(arguments)};` +
    `g("consent","default",{${deniedAds},analytics_storage:"granted"});` +
    `g("consent","default",{${deniedAds},analytics_storage:"denied",region:${regions},wait_for_update:500});` +
    `try{var c=localStorage.getItem(${JSON.stringify(CONSENT_KEY)});` +
    `if(c==="granted"||c==="denied")g("consent","update",{analytics_storage:c})}catch(e){}})();`
  );
}

/** Record the visitor's choice and tell gtag. */
export function applyConsent(choice: ConsentChoice): void {
  try {
    window.localStorage.setItem(CONSENT_KEY, choice);
  } catch {
    // storage blocked: the choice still applies to this page view
  }
  const w = window as Window & { dataLayer?: unknown[] };
  w.dataLayer = w.dataLayer || [];
  (function (..._args: unknown[]) {
    // gtag reads Arguments objects from dataLayer, never plain arrays
    // eslint-disable-next-line prefer-rest-params
    w.dataLayer!.push(arguments);
  })("consent", "update", { analytics_storage: choice });
}

/** Forget the choice so the banner asks again (the footer's "Analytics choice" link). */
export function resetConsent(): void {
  try {
    window.localStorage.removeItem(CONSENT_KEY);
  } catch {
    // nothing stored
  }
}
