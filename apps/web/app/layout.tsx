import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { GoogleAnalytics } from "@next/third-parties/google";
import Providers from "@/app/providers";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { FONT_SCALE_KEY, GA_ID, OG_IMAGE, SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/site";
import "./globals.css";
import "./flash-wizard.css";
import "./verify.css";
import "./status.css";

// Bundled Latin WOFF2 variable fonts keep the shell independent of a remote
// font request. Both families are licensed under the accompanying SIL Open Font
// License; the system fallback covers glyphs outside the Latin subset.
const geist = localFont({
  src: "./fonts/geist-latin.woff2",
  variable: "--font-geist-sans",
  weight: "100 900",
  display: "swap",
});

const geistMono = localFont({
  src: "./fonts/geist-mono-latin.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} — ${SITE_TAGLINE}`,
    template: `%s · ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: `${SITE_NAME} — ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    images: [OG_IMAGE],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME} — ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
    images: [OG_IMAGE.url],
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e9e7e1" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0c0d" },
  ],
};

// Applies the saved text-size before first paint so there is no flash of resized
// text after hydration (next-themes does the same for the theme attribute).
const fontScaleScript = `try{var s=localStorage.getItem(${JSON.stringify(
  FONT_SCALE_KEY,
)});if(s)document.documentElement.style.setProperty("--font-scale",s)}catch(e){}`;
const analyticsQueueScript = GA_ID
  ? `window.__ESP_ATLAS_GA_ID=${JSON.stringify(GA_ID)};window.dataLayer=window.dataLayer||[];try{if(localStorage.getItem("esp-atlas:analytics-disabled")==="1")window["ga-disable-${GA_ID}"]=true}catch(e){}`
  : "";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: fontScaleScript }} />
        {GA_ID && <script dangerouslySetInnerHTML={{ __html: analyticsQueueScript }} />}
        <Providers>
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <SiteHeader />
          {children}
          <SiteFooter />
        </Providers>
      </body>
      {GA_ID && <GoogleAnalytics gaId={GA_ID} />}
    </html>
  );
}
