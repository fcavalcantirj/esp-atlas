import Markdown from "react-markdown";

// The prose below a record's frontmatter. Every record's body starts with
// "# <name>", which the page already shows as its <h1>, so that line is dropped.
export default function PartBody({ body }: { body: string }) {
  const text = body.replace(/^#\s[^\n]*\n+/, "").trim();
  if (!text) return null;
  return (
    <div className="part-prose prose">
      <Markdown>{text}</Markdown>
    </div>
  );
}
