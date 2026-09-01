import { test } from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, renderFaqSection } from "./faq.ts";
import type { FaqItem } from "./api.ts";

// The real generator's output for esp32-c6 as of 2026-08-31 (see
// apps/core/tests/test_faq.py / esp_atlas_core.faq for the live generator) --
// a representative, not live-coupled, fixture: this file only tests the HTML
// renderer's shape and byte cost, not what the Python side produces.
const C6_ITEMS: FaqItem[] = [
  {
    id: "specs",
    question: "What are the ESP32-C6 specs / datasheet?",
    answer:
      "ESP32-C6 is a single-core RISC-V SoC clocked up to 160 MHz, plus a separate low-power RISC-V core up to 20 MHz. It has 512 KB of SRAM (16 KB in the LP domain) and 320 KB of ROM. Radios: Wi-Fi 6, Bluetooth LE 5.3, and an 802.15.4 radio. It exposes native USB (Serial/JTAG).",
  },
  {
    id: "gpio-count",
    question: "What is the ESP32-C6 pinout / GPIO count?",
    answer: "The ESP32-C6 has 30 GPIO pads in total, of which 5 are strapping pins and 2 are tied to USB/flash.",
  },
  {
    id: "radios",
    question: "What wireless radios does the ESP32-C6 have?",
    answer:
      "ESP32-C6's wireless radios: Wi-Fi: Wi-Fi 6 radio. Bluetooth: Bluetooth LE 5.3. 802.15.4: 802.15.4 radio (zigbee-3.0, thread-1.3, matter).",
  },
  {
    id: "lp-core",
    question: "Does the ESP32-C6 have a low-power (LP) core?",
    answer: "Yes -- the ESP32-C6 has a separate RISC-V low-power core clocked up to 20 MHz, alongside its main core (up to 160 MHz).",
  },
  {
    id: "vs-sibling",
    question: "ESP32-C6 vs ESP32-C3: what's different?",
    answer:
      "The ESP32-C6 is a single-core RISC-V SoC at up to 160 MHz (512 KB SRAM); the ESP32-C3 is a single-core RISC-V SoC at up to 160 MHz (400 KB SRAM). " +
      "Wi-Fi: Wi-Fi 6 vs Wi-Fi 4. Bluetooth: BLE 5.3 vs BLE 5. 802.15.4: 802.15.4 yes vs 802.15.4 no. Low-power core: LP core yes vs LP core no.",
  },
];

const MAX_TOTAL_BYTES = 6000;
const MAX_BYTES_PER_ITEM = 1000;

test("escapeHtml escapes the five html-special characters", () => {
  assert.equal(escapeHtml(`<a href="x">&'</a>`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;");
});

test("added HTML bytes stay under the byte budget", () => {
  const html = renderFaqSection(C6_ITEMS);
  const totalBytes = Buffer.byteLength(html, "utf-8");
  assert.ok(totalBytes < MAX_TOTAL_BYTES, `${totalBytes} bytes >= ${MAX_TOTAL_BYTES}`);
  assert.ok(totalBytes < MAX_BYTES_PER_ITEM * C6_ITEMS.length, `${totalBytes} bytes >= ${MAX_BYTES_PER_ITEM * C6_ITEMS.length}`);
});

test("no client JS anywhere in the rendered fragment", () => {
  const html = renderFaqSection(C6_ITEMS);
  assert.ok(!html.includes("<script"));
  for (const tell of ["onclick=", "onload=", "addEventListener", "useState", "useEffect", "import "]) {
    assert.ok(!html.includes(tell), `found client-JS tell: ${tell}`);
  }
});

test("markup is <details>/<summary> only, one pair per item, no <button>", () => {
  const html = renderFaqSection(C6_ITEMS);
  assert.equal((html.match(/<details>/g) ?? []).length, C6_ITEMS.length);
  assert.equal((html.match(/<summary>/g) ?? []).length, C6_ITEMS.length);
  assert.ok(!html.includes("<button"));
});

test("every question and answer appears, HTML-escaped, in the fragment", () => {
  const html = renderFaqSection(C6_ITEMS);
  for (const item of C6_ITEMS) {
    assert.ok(html.includes(escapeHtml(item.question)));
    assert.ok(html.includes(escapeHtml(item.answer)));
  }
});

test("renders nothing for an empty item list", () => {
  assert.equal(renderFaqSection([]), "");
});
