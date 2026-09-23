// react-markdown renders a raw "# Heading" as an <h1>. The detail pages that
// embed foreign markdown (a repo README, a record's prose body) already carry
// their own page-title <h1>, so every ATX heading in the embedded markdown is
// demoted one level here before rendering -- keeping exactly one <h1> per page
// (SEO). Headings inside fenced code blocks are left alone since they're
// example text, not real structure.

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*\S*\s*$/;
const ATX_HEADING = /^( {0,3})(#{1,6})(\s+.*)?$/;
const MAX_LEVEL = 6;

export function demoteMarkdownHeadings(markdown: string): string {
  let fenceMarker: string | null = null;
  return markdown
    .split("\n")
    .map((line) => {
      const fenceMatch = line.match(FENCE);
      if (fenceMatch) {
        const marker = fenceMatch[1][0];
        if (fenceMarker === null) fenceMarker = marker;
        else if (fenceMarker === marker) fenceMarker = null;
        return line;
      }
      if (fenceMarker !== null) return line;
      const headingMatch = line.match(ATX_HEADING);
      if (!headingMatch) return line;
      const [, indent, hashes, rest = ""] = headingMatch;
      return `${indent}${"#".repeat(Math.min(hashes.length + 1, MAX_LEVEL))}${rest}`;
    })
    .join("\n");
}
