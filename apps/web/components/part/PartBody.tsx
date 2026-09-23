import Markdown from "react-markdown";
import { demoteMarkdownHeadings } from "@/lib/markdown-heading-shift";

// The prose below a record's frontmatter. Every record's body starts with
// "# <name>", which the page already shows as its <h1>, so that line is
// dropped; any further heading is demoted so it can't add a second <h1>.
export default function PartBody({ body }: { body: string }) {
  const text = body.replace(/^#\s[^\n]*\n+/, "").trim();
  if (!text) return null;
  return (
    <div className="part-prose prose">
      <Markdown>{demoteMarkdownHeadings(text)}</Markdown>
    </div>
  );
}
