import { test } from "node:test";
import assert from "node:assert/strict";
import {
  RELEVANCE_SORT, apiQueryString, countLine, effectiveSort, emptyCopy, filterCount, firmwareHref, firmwareListRobots,
  filteredLead, firmwareSearchParams, isFiltered, optionLabel, parseFirmwareQuery, socLabel, sortChoices,
} from "./firmware-filters.ts";

const EMPTY = parseFirmwareQuery({});

test("no parameters is the bare list: nothing set, default order, the old request and URL", () => {
  assert.deepEqual(EMPTY, { q: "", board: "", soc: "", category: "", capability: "", tested: false, sort: "" });
  assert.equal(isFiltered(EMPTY), false);
  assert.equal(apiQueryString(EMPTY), "");
  assert.equal(firmwareHref(EMPTY), "/firmware");
  assert.equal(effectiveSort(EMPTY), "popularity");
  assert.equal(firmwareListRobots(EMPTY, true), undefined);
});

test("a query is trimmed, collapsed and capped; filter values must look like ids", () => {
  const q = parseFirmwareQuery({ q: "  ghost   esp  ", board: "M5Cardputer-ADV", soc: "esp32-s3", category: "<script>", capability: ["lora", "gps"], tested: "1" });
  assert.deepEqual(q, { q: "ghost esp", board: "m5cardputer-adv", soc: "esp32-s3", category: "", capability: "lora", tested: true, sort: "" });
  assert.equal(parseFirmwareQuery({ q: "x".repeat(300) }).q.length, 120);
  assert.equal(filterCount(q), 4);
});

test("a query cut at the limit never ends in half an emoji, and every state still encodes", () => {
  const cut = parseFirmwareQuery({ q: "a".repeat(119) + "\u{1F600}" + "tail" });
  assert.equal(Array.from(cut.q).length, 120);
  assert.equal(cut.q.endsWith("\u{1F600}"), true);
  assert.doesNotThrow(() => apiQueryString(cut));
  const lone = parseFirmwareQuery({ q: "bruce \uD83D" });                 // a lone surrogate in the URL
  assert.equal(lone.q, "bruce");
  assert.doesNotThrow(() => firmwareHref(lone));
});

test("a search with no explicit order is by relevance; an explicit order wins; relevance needs words", () => {
  assert.equal(effectiveSort(parseFirmwareQuery({ q: "bruce" })), RELEVANCE_SORT);
  assert.equal(effectiveSort(parseFirmwareQuery({ q: "bruce", sort: "name" })), "name");
  assert.equal(parseFirmwareQuery({ sort: "relevance" }).sort, "");
  assert.equal(parseFirmwareQuery({ sort: "not-a-mode" }).sort, "");
  assert.equal(parseFirmwareQuery({ sort: "popularity" }).sort, "");          // the default is never spelled out
  assert.equal(parseFirmwareQuery({ q: "bruce", sort: "popularity" }).sort, "popularity");   // unless it overrides relevance
});

test("the API query string and the page URL carry exactly what is set, encoded", () => {
  const q = parseFirmwareQuery({ q: "evil portal", board: "m5cardputer", tested: "on", sort: "forks" });
  assert.equal(apiQueryString(q), "?q=evil%20portal&board=m5cardputer&tested=1&sort=forks");
  assert.equal(firmwareHref(q), "/firmware?q=evil%20portal&board=m5cardputer&tested=1&sort=forks");
  assert.equal(firmwareHref(q, { sort: "" }), "/firmware?q=evil%20portal&board=m5cardputer&tested=1");
  assert.equal(firmwareHref(q, { sort: "relevance" }), "/firmware?q=evil%20portal&board=m5cardputer&tested=1");
  assert.equal(firmwareHref(parseFirmwareQuery({ sort: "name" }), { sort: "popularity" }), "/firmware");
});

test("the order control offers Best match only while there are search words", () => {
  assert.deepEqual(sortChoices(EMPTY).map((o) => o.value), ["popularity", "name", "name-desc", "forks", "boards"]);
  assert.equal(sortChoices(parseFirmwareQuery({ q: "bruce" }))[0].value, RELEVANCE_SORT);
});

test("only the bare default list is indexable", () => {
  for (const params of [{ q: "bruce" }, { board: "m5cardputer" }, { tested: "1" }, { sort: "name" }]) {
    assert.deepEqual(firmwareListRobots(parseFirmwareQuery(params), true), { index: false, follow: true });
  }
  assert.deepEqual(firmwareListRobots(EMPTY, false), { index: false, follow: true });
});

test("the count line, the empty state and the labels read like a person wrote them", () => {
  assert.equal(countLine(170, 170, false), "170 firmware projects");
  assert.equal(countLine(12, 170, true), "12 of 170 firmware projects");
  assert.equal(countLine(1, null, false), "1 firmware project");
  assert.equal(filteredLead(3, 170), "Showing 3 of 170 firmware projects — open one to see the boards it has recipes for, by trust tier.");
  assert.equal(filteredLead(0, 170), "Showing 0 of 170 firmware projects.");
  assert.equal(emptyCopy(parseFirmwareQuery({ q: "zzz" })), "No firmware matches “zzz”. Try fewer words or clear a filter.");
  assert.equal(emptyCopy(parseFirmwareQuery({ q: "zzz", soc: "esp32" })), "No firmware matches “zzz” with these filters. Try fewer words or clear a filter.");
  assert.equal(emptyCopy(parseFirmwareQuery({ soc: "esp32" })), "No firmware matches these filters. Try fewer words or clear a filter.");
  assert.equal(optionLabel("ble"), "Bluetooth LE");
  assert.equal(optionLabel("on-device-web-ui"), "On-device web UI");
  assert.equal(optionLabel("bluetooth-proxy"), "bluetooth proxy");
  assert.equal(socLabel("esp32-c6"), "ESP32-C6");
});

test("the tracking event never carries the words searched for", () => {
  const params = firmwareSearchParams(parseFirmwareQuery({ q: "secret thing", board: "m5cardputer" }), 3);
  assert.deepEqual(params, { has_query: true, filters: 1, sort: "relevance", result_count: 3 });
  assert.equal(JSON.stringify(params).includes("secret"), false);
});
