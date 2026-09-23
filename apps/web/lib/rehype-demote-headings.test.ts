import { test } from "node:test";
import assert from "node:assert/strict";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import rehypeRaw from "rehype-raw";
import type { Root, RootContent } from "hast";
import rehypeDemoteHeadings from "./rehype-demote-headings.ts";

function h(tagName: string, children: RootContent[] = []): RootContent {
  return { type: "element", tagName, properties: {}, children } as RootContent;
}

function collectTagNames(tree: Root | RootContent): string[] {
  const names: string[] = [];
  const walk = (node: Root | RootContent) => {
    if (node.type === "element") names.push(node.tagName);
    if ("children" in node) {
      for (const child of node.children) walk(child);
    }
  };
  walk(tree);
  return names;
}

test("rehypeDemoteHeadings shifts a top-level h1 to h2", () => {
  const tree: Root = { type: "root", children: [h("h1", [{ type: "text", value: "Title" }])] };
  rehypeDemoteHeadings()(tree);
  assert.deepEqual(collectTagNames(tree), ["h2"]);
});

test("rehypeDemoteHeadings shifts a nested h1 to h2 and clamps h6 at h6", () => {
  const tree: Root = {
    type: "root",
    children: [h("div", [h("h1", []), h("h6", [])])],
  };
  rehypeDemoteHeadings()(tree);
  assert.deepEqual(collectTagNames(tree), ["div", "h2", "h6"]);
});

test("README pipeline: a markdown '# Foo' and a raw '<h1>Bar</h1>' both demote, leaving zero h1", () => {
  const markdown = "# Foo\n\n<div align=\"center\"><h1>Bar</h1></div>\n";
  const processor = unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeDemoteHeadings);
  const tree = processor.runSync(processor.parse(markdown)) as Root;

  const tagNames = collectTagNames(tree);
  assert.equal(tagNames.filter((t) => t === "h1").length, 0);
  assert.ok(tagNames.includes("h2"), `expected an h2 in ${JSON.stringify(tagNames)}`);
});
