// FAQPage JSON-LD structural validity — promoted from spike/faq-c6/jsonld.py +
// test_jsonld.py (REPORT.md §(b)). Tests faqPage() directly rather than the
// full structured-data.ts partGraph(): partGraph pulls in the rest of the
// app's "@/" import graph (brand/format/routes/github/site), which plain
// `node --test` can't resolve without a bundler (see verify-board.test.ts —
// every testable lib file in this repo avoids runtime "@/" imports for the
// same reason). faqPage() is the exact function partGraph() splices into its
// @graph for a soc with faq items (apps/web/lib/structured-data.ts), so this
// covers the JSON-LD shape completely; only the two-line "when to include it"
// glue in partGraph is left to Next's typecheck + build.
import { test } from "node:test";
import assert from "node:assert/strict";
import { faqPage } from "./faq.ts";
import type { FaqItem } from "./api.ts";

const PART_URL = "https://esp-atlas.com/parts/esp32-c6";
const ITEMS: FaqItem[] = [
  { id: "specs", question: "What are the ESP32-C6 specs / datasheet?", answer: "ESP32-C6 is a single-core RISC-V SoC..." },
  { id: "gpio-count", question: "What is the ESP32-C6 pinout / GPIO count?", answer: "The ESP32-C6 has 30 GPIO pads..." },
  { id: "vs-sibling", question: "ESP32-C6 vs ESP32-C3: what's different?", answer: "The ESP32-C6 is a single-core..." },
];

test("faqPage has the FAQPage/Question/Answer shape schema.org's rich result requires", () => {
  const node = faqPage(PART_URL, ITEMS);
  assert.equal(node["@type"], "FAQPage");
  assert.equal(node["@id"], `${PART_URL}#faq`);
  assert.equal(node.mainEntity.length, ITEMS.length);
  for (const question of node.mainEntity) {
    assert.equal(question["@type"], "Question");
    assert.equal(typeof question.name, "string");
    assert.ok(question.name.length > 0);
    assert.equal(question.acceptedAnswer["@type"], "Answer");
    assert.equal(typeof question.acceptedAnswer.text, "string");
    assert.ok(question.acceptedAnswer.text.length > 0);
  }
});

test("one Question per FAQ item, same order, name/text match 1:1", () => {
  const node = faqPage(PART_URL, ITEMS);
  assert.deepEqual(
    node.mainEntity.map((q) => q.name),
    ITEMS.map((i) => i.question),
  );
  assert.deepEqual(
    node.mainEntity.map((q) => q.acceptedAnswer.text),
    ITEMS.map((i) => i.answer),
  );
});

test("round-trips through JSON.stringify/parse unchanged", () => {
  const node = faqPage(PART_URL, ITEMS);
  const parsed = JSON.parse(JSON.stringify(node));
  assert.deepEqual(parsed, node);
});

test("@id is scoped to the part URL", () => {
  const node = faqPage(PART_URL, ITEMS);
  assert.equal(node["@id"], `${PART_URL}#faq`);
});

test("an empty item list yields an empty mainEntity, not a malformed node", () => {
  const node = faqPage(PART_URL, []);
  assert.equal(node["@type"], "FAQPage");
  assert.deepEqual(node.mainEntity, []);
});
