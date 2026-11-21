# SPEC — Firmware index: search, filters, ordering

Status: v1 (2026-11-19). Owner request: "we need to improve firmware page. no search box, no filter by esp
board … understand how people would search … input to search, and filters, order by". Builds on
`SPEC-firmware-ordering.md` (the API is the only place that filters and orders; the page renders what it returns).

## 0. Grounding (measured 2026-11-19, last 28 days)

- GA4: `/firmware/*` detail pages are 736 of 1,497 page views (49 %). The index `/firmware` had 101 views by 34
  users, `reveal_more` 77 times and `firmware_sort` 16 times: people page through 170 cards because there is
  nothing to type into.
- Search Console, the 52 firmware-shaped queries (160 impressions), by shape:
  - a firmware name alone, 77 impressions ("cathack firmware", "ghost esp", "launcher firmware", "nerdminer v2 firmware");
  - a firmware name and a board, 54 ("meshcore cardputer adv", "evil cardputer", "m5stack meshcore");
  - "firmware for a board", 25 ("cardputer zero firmware", "flipper zero firmware esp32").
  Names are split and misspelled ("ghost esp", "stack chan"), and padded with "firmware", "flasher", "for".
- Catalog (live API): 170 firmware, 348 recipes on 62 boards, 10 chip families, 6 categories, 23 capability
  tags; 45 recipes are `known-good`.

## 1. One search box (`q`)

`GET /firmware?q=…`. Case, accents, spaces and punctuation are ignored ("ghost esp" finds GhostESP). Filler words
are dropped (`firmware`, `for`, `flash`, `flasher`, `install`, …). Every remaining word must be found in the
firmware's own words: its name, id and maintainer; the **ids and names of the boards it has a recipe for**; its
category, capabilities, chip families and distribution; its summary. A board counts with its id, its name and
its maker ("m5stack meshcore"). So "meshcore cardputer adv" finds MeshCore builds that have a recipe for the
Cardputer-Adv, and "cardputer" alone lists everything with a Cardputer recipe. Names, ids and tags match
whatever the spacing ("t deck", "tdeck", "T-Deck"); in a summary a query word must lie inside one word. A
two-character query word must be a whole word or start one ("m5" finds M5Stick; "ir" is the infrared tag, not
part of "Pirate"); a one-character word must be a whole word. Punctuation between words is ignored
("wifi & ble"). A query no record can be found by (non-Latin script, or nothing but punctuation) matches
nothing; a query of filler words only, with or without punctuation, is no query. Every firmware is found by its own name.

Order with `q` and no explicit `sort`: **relevance** (`sort=relevance`): a word found in the name outranks one
found in the id or maintainer, then a board, then a tag, then the summary; a hit at the start of a word counts
double one in the middle of a word; an exact or leading name match first; ties in the popularity order. `relevance` without `q` is the default order.

## 2. Filters

All optional, all combinable with `q` and with each other (AND):

| Param | Keeps a firmware when |
|---|---|
| `board=<board id>` | it has a recipe for that board |
| `soc=<chip family id>` | the family is in its `socs` |
| `category=<category>` | its category equals it |
| `capability=<tag>` | the tag is in its `capabilities` |
| `tested=1` | it has at least one `known-good` recipe (with `board`: a `known-good` recipe for that board) |

An unknown value matches nothing (an empty list, never a 422); a `q` longer than 120 characters is a 422. A
searched or filtered response carries `total` (matches before `limit`/`offset`) and `catalog_total` (the whole
catalog). The bare `GET /firmware` runs on its old code path and returns the same body as before: no
`catalog_total` key.

`GET /firmware/facets` returns the boards (id, name), chip families, categories and capability tags that
exist in the catalog, each with its firmware count, most used first, plus `catalog_total`. Facets describe the
whole catalog, so a control never loses its own options.

**Speed.** Parsing the firmware and recipe files costs over a second per request (measured on the live API,
2026-11-19: `/api/firmware` uncached 1.6 to 2.6 s against 0.33 s for `/api/health`). A search therefore reads
them through `firmware_search.catalog()`, which parses once per state of the files (keyed on every file's
path, size and modification time) and takes board names and makers from the index. Measured locally: first
search 1.9 s, the following ones 16 to 25 ms.

## 3. Page

`/firmware` renders a plain GET form: the search box, the four selects, the "tested on hardware" checkbox, the
sort select, a submit button, and a "clear" link when anything is set. It works with JavaScript off; with it,
changing a select submits the form. Every state is a shareable URL. The count line says "N of 170". No match:
an empty state that names the query and offers to clear it.

SEO: bare `/firmware` stays the indexable canonical; with nothing set its list, metadata and structured data
are what they were (only the control above the list changed). Any
`q`, filter or non-default `sort` renders `noindex, follow` with `canonical → /firmware`.

Controls: a filter picked with a pointer submits at once; one changed from the keyboard waits for the Search
button, so stepping through a select never reloads the page (WCAG 3.2.2). Going Back resets the controls to
the state the URL shows.

Tracking (GA4): `firmware_search` once per searched or filtered list shown, with `has_query`, `filters` (how
many), `sort` and `result_count`; not sent when the list could not be loaded. Never the words typed (the page
URL carries `q`, like the site search: the stream's query-parameter redaction covers it). The "Order by" select replaces the row of
sort links, so `firmware_sort` is no longer sent; an order change on a searched list shows in
`firmware_search.sort`.

## 4. Oracle

Core (`apps/core/tests/test_firmware_search.py`), then API (`apps/api/tests/test_firmware_endpoint.py`), then
the page's pure helpers (`apps/web/lib/firmware-filters.test.ts`). Real-catalog cases are part of the oracle:
"ghost esp" → `ghostesp` first; "meshcore cardputer adv" → only firmware with a recipe for `m5cardputer-adv`;
`board=m5cardputer` → exactly the firmware of the recipes for that board.

## 5. Acceptance

On production after deploy: the queries of §0 return what a person would expect, each filter narrows the list,
the URL round-trips, and the bare page lists what it listed before.
