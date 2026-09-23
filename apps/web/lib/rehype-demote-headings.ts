import type { Element, Root, RootContent } from "hast";

// react-markdown renders README markdown through rehype-raw, which turns any
// raw `<h1>` HTML in the source into a real heading element -- past the point
// where the string-based demoteMarkdownHeadings (markdown-heading-shift.ts)
// can see it. This walks the parsed hast tree instead, so it catches both
// markdown-derived AND raw-HTML headings, keeping exactly one <h1> per page.

const HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"];
const MAX_LEVEL = 6;

function demote(node: Element): void {
  const level = HEADING_TAGS.indexOf(node.tagName);
  if (level !== -1) {
    node.tagName = `h${Math.min(level + 2, MAX_LEVEL)}`;
  }
  for (const child of node.children) {
    if (child.type === "element") demote(child);
  }
}

export default function rehypeDemoteHeadings() {
  return (tree: Root) => {
    for (const child of tree.children as RootContent[]) {
      if (child.type === "element") demote(child);
    }
  };
}
