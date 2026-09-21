// Site-wide constants. NEXT_PUBLIC_* values are inlined at build time, so they
// must be referenced statically (process.env.NEXT_PUBLIC_X), never dynamically.

export const SITE_NAME = "esp-atlas";
export const SITE_EMOJI = "🧭";
export const SITE_TAGLINE = "Which ESP32 for what you're building?";
export const SITE_DESCRIPTION =
  "A community-maintained, datasheet-verified knowledge base of ESP32 SoCs, modules and dev boards. " +
  "Every spec cites an official source. Ask the wizard which ESP32 fits your project.";

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://esp-atlas.com").replace(/\/+$/, "");

// Default social-preview image (public/og-default.png, 1200×630). Pages that
// define their own `openGraph`/`twitter` objects must include it explicitly:
// Next replaces nested metadata objects per segment instead of merging them.
export const OG_IMAGE = {
  url: "/og-default.png",
  width: 1200,
  height: 630,
  alt: `${SITE_NAME} — ${SITE_TAGLINE}`,
};

// WebSite JSON-LD's sitelinks-searchbox action (Google Search Central:
// "Sitelinks Searchbox"): /wizard's free-text search reads `q` off the URL
// on load (ExplorerView), so the template below is a real, working search,
// not just a documented shape.
export function websiteSearchAction() {
  return {
    "@type": "SearchAction" as const,
    target: {
      "@type": "EntryPoint" as const,
      urlTemplate: `${SITE_URL}/wizard?q={search_term_string}`,
    },
    "query-input": "required name=search_term_string",
  };
}

// GA4 measurement ID. Set NEXT_PUBLIC_GA_ID to override; production builds fall
// back to the esp-atlas.com property so a missing Vercel env var never silently
// disables analytics. Dev/preview builds send nothing unless the env var is set.
export const GA_ID: string | undefined =
  process.env.NEXT_PUBLIC_GA_ID || (process.env.NODE_ENV === "production" ? "G-66L7SDXKJZ" : undefined);

// NEXT_PUBLIC_GA_DEBUG=1 tags every event with debug_mode so it shows up in GA4 DebugView.
export const GA_DEBUG = process.env.NEXT_PUBLIC_GA_DEBUG === "1";

// localStorage key for the user's text-size choice (read pre-hydration in app/layout.tsx).
export const FONT_SCALE_KEY = "esp-atlas:font-scale";
