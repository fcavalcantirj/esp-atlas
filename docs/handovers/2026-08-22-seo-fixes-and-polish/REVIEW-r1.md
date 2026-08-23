---
verdict: APPROVED
round: 1
---

# Review r1

Judged only against the acceptance checklist and blocking constraints in `HANDOVER.md`. The Builder's re-verification is better than the handover in four places and is adopted as the new ground truth: `main` = `8b683ee`; `/parts/esp32-s3` has 34 related; the sitemap is 95 URLs so F4's crawl target is 95 and F5's is 107; the CSS anchors shifted by a few lines (`.part-aside` :1265–1270, `.compare-layout` :1566, `.compare-picker` :1576–1581). The new facts matter: `/api/search?brand=` silently ignores the param today (assert counts, never status), every SoC record carries `soc_ref = <own id>`, `ChipChain.tsx:22` nests a second `.chip-chain`, and the serif uppercase labels on `.aside-card h2` / `.spec-group h3` / `.related-group h3` / `.compare-group > summary` are the likeliest reading of "not properly applied on ALL pages".

## Checklist verdicts

1. Seven constraints restated first, own words, each correct (incl. the `origin`-value vs new-parameter distinction and "never on the OG image"): **satisfied**.
2. `[REAL]` claims re-verified with mismatches listed (head SHA, related count, sitemap counts, CSS lines, ld+json tag count) and a "clean" list naming what was checked: **satisfied**.
3. Sweep matrix defined before any fix — 8 routes × 4 widths × 2 themes + 4 state shots, named by path, a CDP measurement script, `findings.md` rows with selector + `globals.css` line: **satisfied**.
4. Fixes (a)–(g) each keep the restyle's system; P2-f (label overline alignment) correctly gated as a visible change; P2-g pixel-diff guard; verification = matrix re-shot + CLS target: **satisfied**.
5. F4: `revalidate = 300`, never-throwing `fetchFacets()`, 11 links labelled "N parts on this chip" (names joined from `fetchAllParts()` SoC records — right, facets carry ids only), SoC `<h2>` only when n > 0, `ItemList`, `"browse"` origin, brand browse deferred, crawl 0 orphans / depth ≤ 2 over 95 URLs: **satisfied**.
6. F5: core `_EXACT_FILTERS` + clause → API param → CLI flag → tests mirroring `soc` in all three suites → `/brands` + `/brands/[brand]` SSR with `generateMetadata`, canonical, restated OG/Twitter, JSON-LD, 404 + noindex for unknown brands, sitemap 107, one footer link: **satisfied**.
7. F6: `opengraph-image.tsx` with `ImageResponse`, awaited `params`, name/brand/SoC/≤3 chips, no `price_tier`, generic card on error (never 500), explicit F1 `images` removed, 5-part spot check: **satisfied**.
8. Sequence polish → F4 → F5 → F6 → (F7 on yes) → docs; `gh pr merge --auto --squash --delete-branch` once green and current, rebase on `strict` stalls, prod verified before the next branch, F4/F6 strictly sequential: **satisfied**.
9. `## Concerns` with severities and `## Questions for the author`; the handover's open questions 1–3 answered as Q1–Q3: **satisfied**.

## Answers to the builder's questions

1. **F7** — default **no**. Ask Felipe once in chat when you report the polish PR; do not add the dependency without an explicit yes.
2. **Chip chain** — yes: shrink-inline as the default, vertical stack shot as the alternative, both before/after pairs shown to Felipe before the polish PR merges (hard rule). If he does not answer within the PR's review, ship shrink-inline.
3. **Sticky** — confirmed: always static for `.part-aside` and `.compare-picker`. Leave `.home-sidebar` as is (no finding).
4. **Compare CLS** — **yes, SSR the picker list**: `app/compare/page.tsx` async with `fetchAllParts()` + `export const revalidate = 300`, `initialParts` prop, client fetch kept as the fallback when the server list is empty. Conditions: `noindex, follow` + canonical `/compare` untouched; all `?ids=` logic stays client-side; the page must never throw (empty list → today's behaviour). This does not reopen the "client-rendered tool" decision — the tool is still client-side; only the static list it starts from is pre-rendered. Report measured CLS either way.
5. **Screenshots** — commit ≤ 6 contact-sheet PNGs (≤ 200 KB each) under `docs/handovers/2026-08-22-seo-fixes-and-polish/assets/` in the polish PR; full sets stay in the scratchpad with paths in the PR body.
6. **F4 placement** — after `<HomeView />` (the wizard is the product; browse links are the crawl path).
7. **F4 SoC aside** — **move, don't duplicate**: on SoC pages the aside "Related parts" card body becomes one line linking to the hub section (`<a href="#on-chip">All N boards and modules on this chip</a>`); boards/modules keep `RelatedParts` unchanged. Two 34-link lists on one page is noise, and the original C4 decision said "promote the list", not "copy it".
8. **F5 matching** — exact `parts.vendor_or_brand = ?`. Slugs are canonical folder names and the route slug comes from the facets, so case-insensitivity buys nothing and would create duplicate URLs.
9. **F5 heading/title** — slug verbatim for this round (`adafruit — ESP32 boards and modules`). A display-name map is editorial naming and belongs in `data/brands/` later — Felipe's call, noted in the docs PR as a follow-up.
10. **Home "Browse by brand"** — yes, in the F5 PR (same component, `origin: "brand"`).
11. **F6 fonts** — default `next/og` font for this round; no per-render network fetch.
12. **F6 JSON-LD** — yes, `TechArticle.image` → the per-part image in the same PR.
13. **`origin` semantics** — OK as stated; add both values to `apps/web/README.md:73` in the PR that introduces each.

## Closing

Builder is now the primary session. First move (the handover's `next_action`): `git fetch origin && git checkout -b polish/editorial-consistency origin/main`, start the API on 8010 and a production build on 3000, shoot the full sweep matrix into the scratchpad, write `findings.md` with CSS line references, fix in `apps/web/app/globals.css` (+ `app/compare/page.tsx` for the skeleton / SSR picker per Q4), re-shoot, open the polish PR with before/after paths and the ≤ 6 contact sheets.
