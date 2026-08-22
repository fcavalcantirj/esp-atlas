// Site-wide constants. NEXT_PUBLIC_* values are inlined at build time, so they
// must be referenced statically (process.env.NEXT_PUBLIC_X), never dynamically.

export const SITE_NAME = "esp-atlas";
export const SITE_EMOJI = "🧭";
export const SITE_TAGLINE = "Which ESP32 for what you're building?";
export const SITE_DESCRIPTION =
  "A community-maintained, datasheet-verified knowledge base of ESP32 SoCs, modules and dev boards. " +
  "Every spec cites an official source. Ask the wizard which ESP32 fits your project.";

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://esp-atlas.com").replace(/\/+$/, "");

// GA4 measurement ID. Set NEXT_PUBLIC_GA_ID to override; production builds fall
// back to the esp-atlas.com property so a missing Vercel env var never silently
// disables analytics. Dev/preview builds send nothing unless the env var is set.
export const GA_ID: string | undefined =
  process.env.NEXT_PUBLIC_GA_ID || (process.env.NODE_ENV === "production" ? "G-66L7SDXKJZ" : undefined);

// NEXT_PUBLIC_GA_DEBUG=1 tags every event with debug_mode so it shows up in GA4 DebugView.
export const GA_DEBUG = process.env.NEXT_PUBLIC_GA_DEBUG === "1";

// localStorage key for the user's text-size choice (read pre-hydration in app/layout.tsx).
export const FONT_SCALE_KEY = "esp-atlas:font-scale";
