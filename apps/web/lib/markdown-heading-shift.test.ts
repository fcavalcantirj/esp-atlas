import { test } from "node:test";
import assert from "node:assert/strict";
import { demoteMarkdownHeadings } from "./markdown-heading-shift.ts";

test("demoteMarkdownHeadings shifts a leading h1 down to h2", () => {
  assert.equal(demoteMarkdownHeadings("# Foo"), "## Foo");
});

test("demoteMarkdownHeadings shifts every ATX heading level by one", () => {
  assert.equal(
    demoteMarkdownHeadings("# One\n\n## Two\n\n### Three"),
    "## One\n\n### Two\n\n#### Three",
  );
});

test("demoteMarkdownHeadings clamps h6 at h6 (there is no h7)", () => {
  assert.equal(demoteMarkdownHeadings("###### Deep"), "###### Deep");
});

test("demoteMarkdownHeadings leaves headings inside a fenced code block untouched", () => {
  const input = "# Real heading\n\n```md\n# not a heading\n```\n\n## Also real";
  const expected = "## Real heading\n\n```md\n# not a heading\n```\n\n### Also real";
  assert.equal(demoteMarkdownHeadings(input), expected);
});

test("demoteMarkdownHeadings preserves indented ATX headings and heading text", () => {
  assert.equal(demoteMarkdownHeadings("  # Indented"), "  ## Indented");
});

test("demoteMarkdownHeadings leaves non-heading lines untouched", () => {
  assert.equal(demoteMarkdownHeadings("Just a paragraph with a # in it, not at line start"), "Just a paragraph with a # in it, not at line start");
});
