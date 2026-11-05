import Link from "next/link";
import HeaderControls from "@/components/HeaderControls";
import AtlasNavLink from "@/components/atlas/AtlasNavLink";
import TrackedLink from "@/components/TrackedLink";
import { contributingUrl, repoUrl } from "@/lib/github";
import { SITE_NAME } from "@/lib/site";

export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="site-header-caption" aria-hidden="true">
        <span>Silicon / Hardware / Firmware</span>
        <span>Every record keeps its evidence.</span>
      </div>
      <div className="site-header-inner">
        <Link href="/" className="site-logo" aria-label={`${SITE_NAME} home`}>
          <svg className="site-logo-mark" viewBox="0 0 32 36" aria-hidden="true" fill="none">
            <path d="M16 4 3 29h26L16 4ZM16 4v25M3 29l20-13M29 29 9 16" stroke="currentColor" strokeWidth="1" />
            <path d="M13.5 1.5h5v5h-5zM.5 26.5h5v5h-5zM26.5 26.5h5v5h-5z" fill="currentColor" />
            <circle cx="16" cy="21" r="2.5" fill="currentColor" />
          </svg>
          <span className="site-logo-text">esp<span className="site-logo-slash">/</span>atlas</span>
        </Link>
        <nav className="site-nav" aria-label="Primary">
          <AtlasNavLink href="/atlas" className="nav-link">Atlas</AtlasNavLink>
          <AtlasNavLink href="/boards" className="nav-link">Boards</AtlasNavLink>
          <AtlasNavLink href="/firmware" className="nav-link">Firmware</AtlasNavLink>
          <AtlasNavLink href="/wizard" className="nav-link">Wizard</AtlasNavLink>
          <AtlasNavLink href="/compare" className="nav-link">Compare</AtlasNavLink>
          <AtlasNavLink href="/how-we-work" className="nav-link">How we work</AtlasNavLink>
          <TrackedLink href={contributingUrl()} linkType="contributing" className="nav-link">
            Add a part
          </TrackedLink>
          <TrackedLink href={repoUrl()} linkType="github_repo" className="nav-link nav-cta">
            GitHub <span aria-hidden="true">↗</span>
          </TrackedLink>
        </nav>
        <HeaderControls />
      </div>
    </header>
  );
}
