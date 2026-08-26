import type { Metadata } from "next";
import Link from "next/link";
import VerifyBoard from "@/components/verify/VerifyBoard";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

// Standalone debug rail (SPEC-verify.md), reusing VerifyBoard's detect-only
// mode: no board prop, so it reads the connected chip and shows the readout
// without an esp-atlas comparison — plus the same serial monitor. The
// board-page usage (VerifyBoard with a board prop -> full match verdict)
// is unchanged.
const TITLE = "Debug — read a chip, watch its serial output";
const DESCRIPTION =
  "Connect any ESP32 over USB to read its chip and watch its serial output. Web Serial, no backend, nothing leaves your browser.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/debug" },
  openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/debug", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
};

export default function DebugPage() {
  return (
    <main id="main" className="container container--narrow" tabIndex={-1}>
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Debug</span>
      </nav>
      <h1>Debug</h1>
      <p className="lead">
        Connect any ESP32 over USB to read its chip and watch its serial output. Web Serial, no backend, nothing leaves your browser.
      </p>
      <VerifyBoard />
    </main>
  );
}
