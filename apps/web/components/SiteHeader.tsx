import Link from "next/link";
import HeaderControls from "@/components/HeaderControls";
import TrackedLink from "@/components/TrackedLink";
import { contributingUrl, repoUrl } from "@/lib/github";
import { SITE_EMOJI, SITE_NAME } from "@/lib/site";

export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link href="/" className="site-logo" aria-label={`${SITE_NAME} home`}>
          <span className="site-logo-mark" aria-hidden="true">
            {SITE_EMOJI}
          </span>
          <span className="site-logo-text">{SITE_NAME}</span>
        </Link>
        <nav className="site-nav" aria-label="Primary">
          <Link href="/" className="nav-link">
            Wizard
          </Link>
          <Link href="/compare" className="nav-link">
            Compare
          </Link>
          <TrackedLink href={contributingUrl()} linkType="contributing" className="nav-link">
            Add a part
          </TrackedLink>
          <TrackedLink href={repoUrl()} linkType="github_repo" className="nav-link nav-cta">
            GitHub
          </TrackedLink>
        </nav>
        <HeaderControls />
      </div>
    </header>
  );
}
