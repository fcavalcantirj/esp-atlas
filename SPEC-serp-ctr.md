# SPEC-serp-ctr — SERP titles, descriptions and the per-chip hub

**Status:** active (restored 2026-11-10; `apps/web/lib/format.ts` has cited this file since the August 2026
SEO audit, but it was never committed). The constraints below are the ones the code already enforces, plus the
chip-hub and `seo_title` rules added for the 2026-11-10 click-through work. On conflict, `SPEC-INDEX.md` wins.

## 1. Why

esp-atlas earns almost every click from firmware pages that rank on page one; parts (chips, boards) rank with
near-zero click-through, and chip queries ("esp32-c6 boards", "esp32-c5 specs") rank around position 50 while
being the largest pool of impressions (GSC, 28 days to 2026-11-09). A title is the one lever that changes
click-through without changing a single verified fact. It is editorial copy, like `price_tier`: it may only
restate facts the record already carries.

## 2. Hard limits (enforced in `apps/web/lib/format.ts`)

- `TITLE_MAX = 60` characters, `DESCRIPTION_MAX = 155`. Every builder truncates at a word boundary and appends
  "…", never mid-word (`truncateAtWord`).
- A title leads with the record's exact `name` (the string people search). When name + benefit overflows, the
  name clause is shortened and the benefit kept (`buildMetaTitle`); a board's exact model/SKU wins over the
  generic benefit (`partMetaTitle`, board branch).
- "pinout" appears in a part title only when `frontmatter.images.pinout` is non-empty (cite-or-omit).
- The root layout appends ` · esp-atlas`; the limit applies to the page's own part.
- Descriptions use the record's own first body sentence (parts) or its grounded `summary` (firmware) when
  present, else a template built only from fields the record carries (`partMetaDescription`,
  `firmwareMetaDescription`). Never a board count or SoC the record does not state.

## 3. `seo_title` override (firmware today, parts from Brief A)

- Opt-in frontmatter field, editorial (not a hard spec, no `sources[]` entry). Empty or absent = formula.
- Must contain the record's `name` verbatim and may contain only facts present in the record (SoCs, board
  count, capabilities, category). A reviewer checks every override against its record before merge.
- Clamped to `TITLE_MAX` at a word boundary; authors write ≤ 60 so nothing is clamped.
- Chosen from evidence, never invented: the input is a committed evidence file (§5) naming the page, its top
  query and its zero-click position; the title carries that query's words next to the name.
- Measured: 14 days after a batch lands, the same window is re-pulled; an override whose page did not gain
  clicks or click-through reverts to the formula.

## 4. The chip hub (`/parts/<soc>`)

- A SoC page is the hub for "<chip> specs, boards and firmware". It already lists every module and board on the
  chip (`SocHub`, from the core's `related`); it also lists **every firmware whose `socs` names the chip**
  ("Firmware for <chip> (n)"), rendered only when n > 0, deterministic from the firmware index.
- Title benefit for a SoC that has related parts: `<specs> SoC: specs, boards, firmware` when the whole title
  fits `TITLE_MAX`, else today's `<specs> SoC specs`. A SoC with no related parts keeps today's title.
- `/boards/<id>` is not a route; detail pages live at `/parts/<id>`. `/boards/:id` redirects permanently to
  `/parts/:id` (`next.config.ts` `redirects()`), so external links to `/boards/esp32-c5` land on the hub.
  `next.config.ts` is deploy-critical: its change needs the owner's explicit go before merge.

## 5. Evidence file for title work

`docs/seo-audit/<YYYY-MM-DD>/page-one-zero-click.json`: a list of objects
`{ "page", "top_query", "impressions", "position", "clicks", "window": {"start","end"} }` pulled from Google
Search Console for pages with position ≤ 10 and clicks = 0 in the window. It is written before any
`seo_title` change and is the baseline of the 14-day re-measure. Pulled by the operator's runner (GSC access
lives there), committed as data.

## 6. Oracle

`apps/web/lib/format.test.ts`: every rule above has a test; a new rule lands with its RED test first (chip-hub
benefit with and without related parts; the 60-char cap on the hub title; part `seo_title` wins, is clamped,
empty falls through byte-identical).
