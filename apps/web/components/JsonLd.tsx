// Server component: emits one JSON-LD block. `<` is escaped so record prose can
// never close the script tag; U+2028/2029 are escaped because they are valid
// JSON but terminate a JavaScript string literal in older parsers.
export default function JsonLd({ data }: { data: object }) {
  const json = JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
