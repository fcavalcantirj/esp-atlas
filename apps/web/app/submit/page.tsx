import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import SubmitForm from "@/components/SubmitForm";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";

const TITLE = "Submit a firmware";
const DESCRIPTION = "Paste a GitHub repository. EspAtlas Jr scores it with the catalog's fixed rules and opens a cited pull request — no login, no account.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/submit" },
  openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/submit", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
};

export default function SubmitPage() {
  const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  return (
    <main id="main" className="container container--narrow" tabIndex={-1}>
      {siteKey && <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js" strategy="afterInteractive" />}
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">Submit</span>
      </nav>
      <h1>Submit a firmware</h1>
      <p className="lead">{DESCRIPTION}</p>
      <SubmitForm siteKey={siteKey} />
      <section id="submit-help">
        <h2>What happens next</h2>
        <ol>
          <li>Your submission becomes a public GitHub issue labelled <code>submission</code>, opened by the EspAtlas Jr bot. That is the only thing this box does.</li>
          <li>Within the hour Jr reads the repository and applies the catalog&apos;s fixed rules — a real public repo, <strong>25 stars or 25 forks</strong>, not a fork of a firmware already listed, and at least one <Link href="/boards">catalogued board</Link> named here or in the repo&apos;s own release assets and <code>platformio.ini</code>. No AI decides anything.</li>
          <li>Jr comments the verdict on the issue. If it passes, Jr opens a pull request with a cited firmware record and its first recipe; CI must be green and a human can still veto. Then it maps every board the repo&apos;s build files name.</li>
        </ol>
        <p>
          Prefer GitHub? <a href="https://github.com/fcavalcantirj/esp-atlas/issues/new?template=submission.yml">Open the submission issue yourself</a> — same gate, same bot.
          Nothing typed here is stored by this site. <Link href="/how-we-work">How we work →</Link>
        </p>
      </section>
    </main>
  );
}
