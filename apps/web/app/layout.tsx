import type { Metadata, Viewport } from "next";
import { Newsreader, Geist_Mono } from "next/font/google";
import { GoogleAnalytics } from "@next/third-parties/google";
import Providers from "@/app/providers";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { FONT_SCALE_KEY, GA_ID, OG_IMAGE, SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from "@/lib/site";
import "./globals.css";
import "./flash-wizard.css";
import "./verify.css";
import "./status.css";

// Language is set in a high-contrast serif; data is set in mono. Two voices only.
const newsreader = Newsreader({
  variable: "--font-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1115" },
  ],
};

// Applies the saved text-size before first paint so there is no flash of resized
// text after hydration (next-themes does the same for the theme attribute).
const fontScaleScript = `try{var s=localStorage.getItem(${JSON.stringify(
  FONT_SCALE_KEY,
)});if(s)document.documentElement.style.setProperty("--font-scale",s)}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${newsreader.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: fontScaleScript }} />
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
