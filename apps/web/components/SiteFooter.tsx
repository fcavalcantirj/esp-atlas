import Link from "next/link";
import TrackedLink from "@/components/TrackedLink";
import { agentsUrl, contributingUrl, dataFolderUrl, discussionsUrl, issuesUrl, licenseUrl, repoUrl } from "@/lib/github";
import { SITE_NAME } from "@/lib/site";

const API_DOCS_PATH = "/api/docs";
const LLMS_TXT_PATH = "/llms.txt";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-grid">
          <section className="footer-col footer-col--about" aria-label={`About ${SITE_NAME}`}>
            <Link href="/" className="footer-wordmark" aria-label={`${SITE_NAME} home`}>
              esp<span>/</span><wbr />atlas
            </Link>
            <p className="footer-standfirst">Every ESP32, mapped and cited.</p>
            <p className="footer-summary">
              Find the board. See what runs. Flash it. Debug it.
              Every record keeps its sources; every recipe shows its trust tier.
            </p>
            <Link href="/how-we-work" className="footer-how">How we work <span aria-hidden="true">↗</span></Link>
            <p className="footer-contact"><a href="mailto:hello@esp-atlas.com">hello@esp-atlas.com</a></p>
          </section>

          <section className="footer-col" aria-labelledby="footer-explore">
            <h2 className="footer-title" id="footer-explore">Explore</h2>
            <ul className="footer-links">
              <li><Link href="/atlas">The interactive atlas</Link></li>
              <li><Link href="/">Wizard &amp; search</Link></li>
              <li><Link href="/boards">Boards &amp; hardware</Link></li>
              <li><Link href="/firmware">Firmware &amp; flashing</Link></li>
              <li><Link href="/compare">Compare parts</Link></li>
              <li><Link href="/brands">Brands</Link></li>
              <li><Link href="/debug">Debug</Link></li>
              <li><Link href="/status">Status</Link></li>
            </ul>
          </section>

          <section className="footer-col" aria-labelledby="footer-contribute">
            <h2 className="footer-title" id="footer-contribute">Contribute</h2>
            <ul className="footer-links">
              <li><Link href="/submit">Submit a firmware</Link></li>
              <li><TrackedLink href={contributingUrl()} linkType="contributing">Add or fix a part</TrackedLink></li>
              <li><TrackedLink href={discussionsUrl()} linkType="discussions">Suggestions &amp; questions</TrackedLink></li>
              <li><TrackedLink href={issuesUrl()} linkType="issues">Report a bug or wrong spec</TrackedLink></li>
              <li><TrackedLink href={agentsUrl()} linkType="agents">AGENTS.md for coding agents</TrackedLink></li>
            </ul>
          </section>

          <section className="footer-col" aria-labelledby="footer-data">
            <h2 className="footer-title" id="footer-data">Data &amp; code</h2>
            <ul className="footer-links">
              <li><TrackedLink href={dataFolderUrl()} linkType="data_folder">Browse the dataset</TrackedLink></li>
              <li><TrackedLink href={repoUrl()} linkType="github_repo">Source repository</TrackedLink></li>
              <li><TrackedLink href={API_DOCS_PATH} linkType="api_docs">API documentation</TrackedLink></li>
              <li><TrackedLink href={LLMS_TXT_PATH} linkType="llms_txt">llms.txt</TrackedLink></li>
            </ul>
          </section>
        </div>

        <div className="footer-bottom">
          <span>
            Data (<code>data/</code>, <code>schema/</code>):{" "}
            <TrackedLink href="https://creativecommons.org/licenses/by-sa/4.0/" linkType="license">CC-BY-SA 4.0</TrackedLink>
            {" · "}Code: <TrackedLink href={licenseUrl()} linkType="license">MIT</TrackedLink>
          </span>
          <span>Flash &amp; verify need a Chromium browser (Chrome, Edge).</span>
          <span>Uses Google Analytics to learn how people search for parts.</span>
        </div>
      </div>
    </footer>
  );
}
