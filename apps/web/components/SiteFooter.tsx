import Link from "next/link";
import TrackedLink from "@/components/TrackedLink";
import {
  agentsUrl,
  contributingUrl,
  dataFolderUrl,
  discussionsUrl,
  issuesUrl,
  licenseUrl,
  llmsTxtUrl,
  repoUrl,
} from "@/lib/github";
import { SITE_NAME } from "@/lib/site";

const API_DOCS_PATH = "/api/docs";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-grid">
          <section className="footer-col footer-col--about">
            <h2 className="footer-title">Why {SITE_NAME}</h2>
            <p className="footer-standfirst">
              A community wiki for ESP32 hardware, <em>cited to the datasheet</em>.
            </p>
            <p>
              Picking an ESP32 board means wading through dozens of near-identical models from a dozen vendors,
              each documented in a different place. We — Felipe and his coding agent — kept losing hours to it,
              so we built the community wiki we wished existed: every spec cited to an official datasheet,
              queryable, and fixable by pull request.
            </p>
            <p>
              If it isn&apos;t verified, it isn&apos;t stated. Found a wrong number or a missing board? That&apos;s a
              one-file PR away.
            </p>
          </section>

          <section className="footer-col">
            <h2 className="footer-title">Contribute</h2>
            <ul className="footer-links">
              <li>
                <TrackedLink href={contributingUrl()} linkType="contributing">
                  Add or fix a part
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={discussionsUrl()} linkType="discussions">
                  Suggestions &amp; questions
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={issuesUrl()} linkType="issues">
                  Report a bug or wrong spec
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={agentsUrl()} linkType="agents">
                  AGENTS.md for coding agents
                </TrackedLink>
              </li>
            </ul>
          </section>

          <section className="footer-col">
            <h2 className="footer-title">Data &amp; code</h2>
            <ul className="footer-links">
              <li>
                <TrackedLink href={dataFolderUrl()} linkType="data_folder">
                  Browse the dataset on GitHub
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={repoUrl()} linkType="github_repo">
                  Source repository
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={API_DOCS_PATH} linkType="api_docs">
                  API docs
                </TrackedLink>
              </li>
              <li>
                <TrackedLink href={llmsTxtUrl()} linkType="llms_txt">
                  llms.txt
                </TrackedLink>
              </li>
            </ul>
          </section>

          <section className="footer-col">
            <h2 className="footer-title">Explore</h2>
            <ul className="footer-links">
              <li>
                <Link href="/">Wizard &amp; search</Link>
              </li>
              <li>
                <Link href="/compare">Compare parts</Link>
              </li>
              <li>
                <Link href="/parts/esp32-c6">ESP32-C6</Link> · <Link href="/parts/esp32-s3">ESP32-S3</Link> ·{" "}
                <Link href="/parts/esp32-h2">ESP32-H2</Link>
              </li>
            </ul>
          </section>
        </div>

        <div className="footer-bottom">
          <span>
            Data (<code>data/</code>, <code>schema/</code>) is{" "}
            <TrackedLink href="https://creativecommons.org/licenses/by-sa/4.0/" linkType="license">
              CC-BY-SA 4.0
            </TrackedLink>
            ; code is{" "}
            <TrackedLink href={licenseUrl()} linkType="license">
              MIT
            </TrackedLink>
            .
          </span>
          <span className="muted">Uses Google Analytics to learn how people search for parts.</span>
        </div>
      </div>
    </footer>
  );
}
