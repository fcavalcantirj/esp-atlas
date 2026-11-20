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
category, capabilities, chip families and distribution; its summary. So "meshcore cardputer adv" finds MeshCore
builds that have a recipe for the Cardputer-Adv, and "cardputer" alone lists everything with a Cardputer recipe.

Order with `q` and no explicit `sort`: **relevance** (`sort=relevance`): a word found in the name outranks one
found in the id or maintainer, then a board, then a tag, then the summary; an exact or leading name match first;
ties in the popularity order. `relevance` without `q` is the default order.

## 2. Filters

All optional, all combinable with `q` and with each other (AND):

| Param | Keeps a firmware when |
|---|---|
| `board=<board id>` | it has a recipe for that board |
| `soc=<chip family id>` | the family is in its `socs` |
| `category=<category>` | its category equals it |
| `capability=<tag>` | the tag is in its `capabilities` |
| `tested=1` | it has at least one `known-good` recipe (with `board`: a `known-good` recipe for that board) |

An unknown value matches nothing (an empty list, never a 422). The response carries `total` (matches before
`limit`/`offset`), `catalog_total` (the whole catalog) and `facets`: the boards, chip families, categories and
capability tags that exist in the catalog with their firmware counts, for the filter controls. Facets describe
the whole catalog, so a control never loses its own options.

## 3. Page

`/firmware` renders a plain GET form: the search box, the four selects, the "tested on hardware" checkbox, the
sort select, a submit button, and a "clear" link when anything is set. It works with JavaScript off; with it,
changing a select submits the form. Every state is a shareable URL. The count line says "N of 170". No match:
an empty state that names the query and offers to clear it.

SEO: bare `/firmware` stays the indexable canonical and is byte-identical to before when nothing is set. Any
`q`, filter or non-default `sort` renders `noindex, follow` with `canonical → /firmware`.

Tracking (GA4, no free text of the query beyond what `search_submit` already sends elsewhere):
`firmware_search` (`has_q`, `filters` count, `results`), on submit.

## 4. Oracle

Core (`apps/core/tests/test_firmware_search.py`), then API (`apps/api/tests/test_firmware_endpoint.py`), then
the page's pure helpers (`apps/web/lib/firmware-filters.test.ts`). Real-catalog cases are part of the oracle:
"ghost esp" → `ghostesp` first; "meshcore cardputer adv" → only firmware with a recipe for `m5cardputer-adv`;
`board=m5cardputer` → exactly the firmware of the recipes for that board.

## 5. Acceptance

On production after deploy: the queries of §0 return what a person would expect, each filter narrows the list,
the URL round-trips, and the bare page is unchanged.
