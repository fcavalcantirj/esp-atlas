import Markdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { type Options as SanitizeSchema } from "rehype-sanitize";
import TrackedLink from "@/components/TrackedLink";
import type { Firmware } from "@/lib/api";
import { readmeLanguageName } from "@/lib/format";
import { resolveReadmeHref, type RepoReadme } from "@/lib/readme";
import rehypeDemoteHeadings from "@/lib/rehype-demote-headings";

// The inline README permits formatting but no script, iframe, or event handler.
const README_HTML_SCHEMA: SanitizeSchema = {
  tagNames: [
    "br", "p", "a", "b", "strong", "i", "em", "code", "pre", "ul", "ol", "li",
    "blockquote", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead",
    "tbody", "tr", "th", "td",
  ],
  attributes: { a: ["href", "title"] },
  protocols: { href: ["http", "https", "mailto"], src: ["http", "https"] },
  strip: ["script", "style", "iframe"],
};

export default function FirmwareReadme({ firmware, readme }: { firmware: Firmware; readme: RepoReadme | null }) {
  const translatedReadme = firmware.readme_en;
  if (!translatedReadme && !readme) return null;

  return (
    <section className="firmware-readme" aria-labelledby="firmware-readme">
      <p className="firmware-readme-label" id="firmware-readme">README</p>
      {translatedReadme && (
        <p className="firmware-dek-marker muted">machine-translated from {readmeLanguageName(firmware.readme_lang ?? "")}</p>
      )}
      <div className="firmware-readme-collapse">
        <div className="firmware-readme-body">
          <Markdown
            rehypePlugins={[rehypeRaw, rehypeDemoteHeadings, [rehypeSanitize, README_HTML_SCHEMA]]}
            components={{ a: ({ href, title, children }) => {
              const target = resolveReadmeHref(href ?? "", readme, firmware.url);
              return target
                ? <a href={target} title={title}>{children}</a>
                : <span title="This link is unavailable in the upstream repository">{children}</span>;
            } }}
          >
            {translatedReadme ?? readme!.markdown}
          </Markdown>
        </div>
      </div>
      <p>
        <TrackedLink href={firmware.url} linkType="source" extra={{ firmware_id: firmware.id, from: "readme" }}>
          {translatedReadme ? "Read the original README on GitHub" : "Read the full README on GitHub"}
        </TrackedLink>
      </p>
      {!translatedReadme && readme && (
        <p className="firmware-readme-caption muted">source github.com/{readme.owner}/{readme.repo}</p>
      )}
    </section>
  );
}
