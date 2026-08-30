import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import TrackedLink from "@/components/TrackedLink";
import { viewSourceUrl, viewTreeUrl } from "@/lib/github";
import { OG_IMAGE, SITE_NAME } from "@/lib/site";
import { howWeWorkGraph } from "@/lib/structured-data";

// The project's account of itself. Copy is final and rendered verbatim
// (architect brief, 2026-08-24); this file only sets it in the type system.
const TITLE = "How esp-atlas works";
const DESCRIPTION =
  "A small agent watches the ESP32 world every day and proposes what changed; humans review it; nothing lands without a source. What esp-atlas promises, and what it doesn't.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/how-we-work" },
  openGraph: { type: "website", siteName: SITE_NAME, title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, url: "/how-we-work", images: [OG_IMAGE] },
  twitter: { card: "summary_large_image", title: `${TITLE} · ${SITE_NAME}`, description: DESCRIPTION, images: [OG_IMAGE.url] },
};

export default function HowWeWorkPage() {
  return (
    <main id="main" className="container container--narrow prose" tabIndex={-1}>
      <JsonLd data={howWeWorkGraph(DESCRIPTION)} />
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">›</span>
        <span aria-current="page">How we work</span>
      </nav>
      <h1>How esp-atlas works</h1>
      <p className="lead">
        There is more ESP32 information than any of us can read. New boards, new firmware, new recipes appear every
        week across a hundred repos, forums, and vendor pages — and most guides are one person&apos;s blog, frozen the
        day it was published. esp-atlas is an attempt to keep up, honestly. A small agent watches those sources every
        day and proposes what changed; humans review it; nothing lands without a source. The result is a public map
        of the ESP32 family — which chip or board to buy and <em>why</em>, and firmware recipes that someone actually
        flashed — that you can query, and that anyone can correct with a pull request. We won&apos;t have everything.
        We&apos;d rather say &lsquo;not verified&rsquo; than guess.
      </p>

      <h2>Why</h2>
      <p>
        The ESP32 family is enormous and moving fast: dozens of chips, hundreds of boards, thousands of firmware
        projects and forum threads. In the AI age there is no shortage of information — the shortage is <em>trust</em>.
        Specs get copy-pasted wrong, recipes rot when firmware updates, and every guide freezes at its publish date.
      </p>

      <h2>What esp-atlas is</h2>
      <p>
        A shared, public knowledge base that answers &lsquo;which ESP should I buy for X, and why?&rsquo; and hands you a
        firmware or wiring recipe that has been tested. Every hard spec cites an official source. The data is plain
        markdown in a git repo, so a wrong number is a bug and a missing board is one PR away.
      </p>

      <h2>How it stays alive — meet EspAtlas Jr. 🤖</h2>
      <p>
        Nobody can curate this by hand, so we don&apos;t pretend to. <strong>EspAtlas Jr.</strong>, our autonomous
        data-maintainer, runs every day: it checks that sources are still alive, watches firmware releases, notices when
        a recipe has drifted, and discovers new boards and projects from official catalogs and community signal. It
        never writes to main. It opens pull requests with a citation attached, and a human decides. Auto-harvested
        recipes land marked <em>unverified</em> until someone with the hardware confirms them. Staleness is shown, not
        hidden.
      </p>
      <ul className="how-links" aria-label="EspAtlas Jr. links">
        <li>
          <TrackedLink href={viewSourceUrl("SPEC-espatlas-jr.md")} linkType="github_view" extra={{ doc: "SPEC-espatlas-jr.md" }}>
            How it&apos;s specced
          </TrackedLink>
        </li>
        <li>
          <TrackedLink href={viewSourceUrl("seeds.json")} linkType="github_view" extra={{ doc: "seeds.json" }}>
            The sources it watches (seeds)
          </TrackedLink>
        </li>
        <li>
          <TrackedLink href={viewTreeUrl(".maintainer")} linkType="github_view" extra={{ doc: ".maintainer" }}>
            Its daily prompt
          </TrackedLink>
        </li>
      </ul>

      <h2>What we promise, and what we don&apos;t</h2>
      <p>
        We promise every stated spec has a source, every recipe shows its trust level, and every mistake can be fixed
        by anyone. We don&apos;t promise completeness or perfection — the atlas is only as good as its last daily run
        and its last reviewer. If the data can&apos;t support an answer, it says so.
      </p>
      <p>Fix it, extend it, argue with it. It&apos;s yours as much as ours.</p>
    </main>
  );
}
