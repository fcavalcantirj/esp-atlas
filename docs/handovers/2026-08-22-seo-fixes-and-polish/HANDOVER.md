---
slug: seo-fixes-and-polish
date: 2026-08-22
status: open            # open → in_review → approved | escalated
round: 0
author_session: builder session of 2026-08-22-seo-audit-and-restyle (shipped PRs #3–#7, wrote docs/seo-audit/2026-08-22.md); context at 67% at hand-off
---

# Handover — SEO fix series (F4–F6) + UI polish on esp-atlas.com

## Mission

Fresh session in `/Users/fcavalcanti/dev/esp-atlas` (GitHub `fcavalcantirj/esp-atlas`, production https://esp-atlas.com). Two work items, both from Felipe:

**(A) UI polish — his words, 2026-08-22:** *"Look&feel not properly applied on ALL pages, and scroll - without the need of scroll, some pages overflowing. the polish you know?"* The editorial restyle (PR #3: Newsreader serif for language, Geist Mono for data, squared radii, flat header, type-scale tokens) must read as one system on **every** route and viewport; no nested scrollbars where the page should scroll; nothing overflowing on phones. Scope is web-only (`apps/web/app/globals.css` and component markup); no data logic.

**(B) Finish the approved "ship now" SEO series** from `docs/seo-audit/2026-08-22.md` §13: PR-F4 (crawlable home + SoC hubs), PR-F5 (core `brand` filter → `/brands` pages), PR-F6 (per-part OG image), the compare clipping + CLS fix (Felipe said yes), PR-F7 only if Felipe says yes. One concern per PR, each green, **auto-merged when `schema`+`tests` pass** (Felipe: "merge all" → "Auto-merge when green"), verified on production after each merge.

"Done" = every route and viewport in the polish matrix signed off with screenshots; F4, F5, F6 and the compare fix live on esp-atlas.com with the post-merge checks passing; the audit's §13 table A rows updated to "merged" in a final docs PR.

## Where things stand (verified)

### Repo, PRs, production
- [REAL] `main` = `5286632` at hand-off (2026-08-23 ~00:10 UTC); merged 2026-08-22: #3 restyle (`db10804`), #4 `ci: run validate on every pull request` (`782f61a` — CI now runs on every PR; docs-only PRs merge), #5 audit doc + first handover dir (`000ff17`), #6 PR-F1 metadata hygiene (`9430a49`), #7 PR-F2 JSON-LD (`ee2bf33`), #8 PR-F3 sitemap lastmod + `/llms.txt` (`5286632`). No open PRs except this handover's own docs PR (auto-merged when green). Verify first: `git log origin/main --oneline -5` and `gh pr list -R fcavalcantirj/esp-atlas --state all --limit 10`.
- [REAL] Production after F1–F3 (curl 2026-08-22/23): `/` and every part page carry one `application/ld+json` block (Organization + WebSite + Dataset on `/`; Organization + WebSite + TechArticle + BreadcrumbList on parts); `/llms.txt` 200 `text/plain`; sitemap 95 `<loc>` with 95 `<lastmod>`, `/compare` absent; `/` has `<link rel="canonical" href="https://esp-atlas.com">`, `twitter:card summary_large_image`, `og:image` `/og-default.png` (200, 27 938 B); `/compare?ids=…` has `<meta name="robots" content="noindex, follow">` + canonical `/compare` + own `og:url`; part pages carry their own `twitter:title`, `og:site_name`, `og:url`, `og:image`; footer column titles are `<p class="footer-title">`; `.chip-chain-item--current .badge` at full contrast; `/parts/nope` 404 + noindex; sitemap was 96 `<loc>` before F3.
- [REAL] Branch protection: required checks `schema`, `tests`; `strict: true` (branch must be current with `main` — rebase before merge); `enforce_admins: true`; 0 reviews. Squash-merge: `gh pr merge N -R fcavalcantirj/esp-atlas --squash --delete-branch`.
- [REAL] `gh` keyring: `fcavalcanti-onvida` (active, **no push/admin**) and `fcavalcantirj` (owner). Every PR create/merge and repo-settings call:
  ```
  gh auth switch --user fcavalcantirj
  # … gh pr create / gh pr merge …
  gh auth switch --user fcavalcanti-onvida
  ```
  Read-only owner calls without switching: `GH_TOKEN=$(gh auth token --user fcavalcantirj) gh api …`. `git push` over SSH is already `fcavalcantirj`.
- [REAL] Audit: `docs/seo-audit/2026-08-22.md` (1,774 lines; §13 = action plan with files/PR/effort/owner/success-metric per row; §2 "Mobile responsiveness", §7 and §13 table C hold the mobile findings). Scorecard 42/100 → ≈68 after the series.

### Polish — what Felipe's screenshots show and what the CSS says
- [REAL] **Nested scrollbar in the part-page aside (desktop)**: `apps/web/app/globals.css:1260–1269` — inside `@media (min-width: 1024px)` `.part-aside { position: sticky; top: …; max-height: calc(100dvh - var(--header-h) - 2rem); overflow-y: auto }`. The aside (Sources / Contribute / Related parts — 33 links on ESP32-S3 boards) scrolls inside itself. Same pattern on `.compare-picker` at `:1579–1580`. Felipe: *"scroll - without the need of scroll"* → these inner scroll containers are the target.
- [REAL] **Phone `/compare` overflows** (screenshot + CDP measurement during the restyle QA): `.compare-layout { grid-template-columns: 1fr }` (`:1565`) lets the spec table's min-content (150 + 3×160 px) widen the column to ~686 px in a 360 px content box; `html, body { overflow-x: hidden }` clips it — picker input/tabs cut, Clear off-screen, table columns 2–3 unreachable. Fix agreed by Felipe: `.compare-layout { grid-template-columns: minmax(0, 1fr) } .compare-layout > * { min-width: 0 }` + give the Suspense fallback in `apps/web/app/compare/page.tsx` the layout's footprint (skeleton picker + `min-height` on the table area) so `footer.site-footer` stops jumping (PSI CLS 0.591 mobile / 0.278 desktop — the only failing CWV).
- [REAL] **Phone part page "Built on" chain wraps badly** (screenshot): `.chip-chain` (`:1319`) is `display: flex; flex-wrap: wrap` with no narrow-width rule; the current chip stretches to full width with its kind badge pushed to the far right, the `.chip-chain-arrow` lands alone on the next line, then the SoC chip. The breadcrumb (`.breadcrumb`, `:1239`, `flex-wrap: wrap`) wraps the part name onto its own line — acceptable or not is a design read; include in the sweep.
- [REAL] Other mobile measurements from the restyle QA (CDP at 390 px): footer gutter 18.75 px vs 15 px for header/main below 600 px (`--page-x` not overridden in the `@media (max-width: 599px)` block); smallest UI text ~10.3 px (`.btn--sm`, `.footer-bottom`); inputs/selects 11.25 px (`--t-xs` on the 15 px root → iOS focus-zoom; **the 16 px floor is Felipe's call, not chosen yet**); the `/compare` `.segmented` control stretches to the picker width (inline-flex child of a column flex parent); header at 390 px wraps the nav to a second row (intended). `/`, part pages: no horizontal overflow at 390 px; light/dark parity held.
- [UNVERIFIED] Which pages Felipe means by *"not properly applied on ALL pages"* beyond these: candidates are `app/not-found.tsx` and `app/error.tsx` (`container container--narrow`, `lead`, `btn`), `PartDetailClient` loading/error states, module pages (`/parts/esp32-c6-wroom-1`), chip-only SoC pages (`/parts/esp32-c5`: "No other parts on this chip yet"), and every route at 768/1024 px (never screenshotted this session — only 390 and 1440). The sweep below settles it.

### Code facts for F4/F5 (read this session, 2026-08-22; line numbers at `main` 9430a49 — re-check after F2/F3 shifted `app/page.tsx`, `app/parts/[id]/page.tsx`, `sitemap.ts`, `SiteFooter.tsx`)
- [REAL] `apps/web/lib/api-server.ts` (58 lines): `serverFetch<T>(path)` is **private**, never throws (`{status: "ok"|"not_found"|"error"}`), 1 h `revalidate`, `TIMEOUT_MS = 3000`; exports `fetchPartDetail(id)` and `fetchAllParts()` (returns `[]` on failure). No search/facets helper — `fetchFacets()` is new code.
- [REAL] `/facets` returns 8 keys of `{value, count}` (`apps/api/src/esp_atlas_api/models.py:66-79`; core `apps/core/src/esp_atlas_core/facets.py:15-25`). **`soc_ref` values are bare ids only — no SoC display name**; for "Browse by chip" names, use `fetchAllParts()` filtered to `type === "soc"` (carries `name`) and join on id. `soc_ref` counts exclude the SoC's own row only if the SoC record has no `soc_ref`; label "N parts on this chip" either way.
- [REAL] `apps/web/app/page.tsx` is a server component with no fetch (no `revalidate` export yet); `HomeView.tsx` is `"use client"` and fetches `/facets` client-side for the forms only (`soc_ref` unused there).
- [REAL] `components/part/PartDetailView.tsx` (server-safe): `.part-layout` → `.part-main` (header, chain, body, specs, notes) + `<aside className="part-aside">` with three `.aside-card` `<h2>` blocks; "Related parts" renders `components/part/RelatedParts.tsx` (`"use client"`): groups `part.related` by type, `<h3>{typePlural(type)} on {socName} ({n})</h3>` + `<ul className="related-list">` links firing `track("result_click", {…, origin: "related", position})`. `part.related` comes from core `get_part()` (`search.py:193-199`, uncapped, `ORDER BY type, name`).
- [REAL] `lib/analytics.ts:49` `export type ResultOrigin = "wizard" | "search" | "related" | "compare" | "chain";` — add `"browse"` (and `"brand"` for F5); only `PartResultCard` enforces the type, `RelatedParts`/`CompareTable` pass string literals.
- [REAL] Core filters: `apps/core/src/esp_atlas_core/search.py:17-19` — `_EXACT_FILTERS = {"type","form","soc","module"}` is **declared but never referenced**; `_KNOWN_FILTERS = _BOOL_FILTERS | _EXACT_FILTERS | {"band","protocol","radio"}` is what `_validate_filters` (L37-40) checks. `_build_where` (L56-94) adds one clause per filter: `form` L67-69 uses `LOWER(parts.form_factor) = LOWER(?)`, `soc` L70-72 `parts.soc_ref = ?`. A `brand` filter = add to `_EXACT_FILTERS` **and** a clause `parts.vendor_or_brand = ?` in `_build_where`. `vendor_or_brand` is already in `_row_to_record` (L110) and comes from `index_build.py:69` (`fm.get("vendor") or fm.get("brand")`); distinct values = folder slugs (`espressif` 30, `m5stack` 11, `adafruit` 11, `lilygo` 9, `lolin` 6, `dfrobot` 6, `sparkfun` 5, `heltec` 5, `unexpected-maker` 4, `soldered` 4, `seeed` 3).
- [REAL] API `/search` (`main.py:70-114`): one `Optional[...]` param per filter + `if x is not None: filters["x"] = x`; `ValueError` → 400. CLI `search` (`apps/cli/src/esp_atlas_cli/main.py:30-59`): click options `--radio --band --form --protocol --type --soc` (no `--module`), truthy → `filters[...]`, `ValueError` → `ClickException`; `_print_records` (L62-79) does not print brand.
- [REAL] Tests to mirror: core `apps/core/tests/test_search.py:140-146` `test_search_soc_filter_returns_only_parts_on_that_soc` (fixture `built_db_path`); API `apps/api/tests/test_app.py:331-337` `test_search_soc_filter` (fixture `client` = `TestClient(create_app(db_path=built_db_path))`); CLI `apps/cli/tests/test_cli.py:208-213` `test_search_command_soc_filter` (helper `run(args, db_path)` wrapping `CliRunner`). `test_wizard_oracle.py` enumerates wizard needs only — a search-only `brand` filter needs no registration there; `test_facets.py` asserts the 8 facet keys (unchanged).
- [REAL] Web: `lib/api.ts:72-85` `SearchFilters` has no `brand` (add it); `searchParts()` L139-141 is client-only; no `/brands` route exists; footer "Explore" block is `components/SiteFooter.tsx:91-105`; `sitemap.ts` appends into `[...staticRoutes, ...partRoutes]` (L39) — brand slugs are available from `fetchAllParts()` records' `vendor_or_brand`; root `llms.txt:19` lists the API params (update when `brand=` lands). No JS test suite exists in `apps/web`.

### Analytics / Search Console (no code)
- [REAL] GA4 property `551132215`, stream `15482230279`, `G-66L7SDXKJZ`; 33 event-scoped dimensions + 7 metrics registered (13 dims + `count` added today); key events `result_click`, `outbound_click` created. Service-account key **revoked** (0 user keys on `esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com`); PSI API key **deleted**. APIs enabled on GCP project `esp-atlas-ga4`: analyticsadmin, analyticsdata, searchconsole, pagespeedonline, apikeys. To use them again, Felipe mints a key (`gcloud iam service-accounts keys create /tmp/ga4-sa.json --iam-account=esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com --project esp-atlas-ga4`) and it is revoked after use.
- [REAL] GSC `sc-domain:esp-atlas.com`: SA added as Restricted (read-only); Felipe submitted `https://esp-atlas.com/sitemap.xml` on 2026-08-22 — the UI showed "Couldn't fetch", *Last read* empty, *Type* Unknown. From our side the sitemap is 200, `application/xml`, valid, 96 URLs, 0.33–0.40 s as Googlebot, no BOM — the status is GSC's pre-processing placeholder on a brand-new property. Re-check after ~24 h; if unchanged, remove + re-add. Owner actions still open: GSC↔GA4 link (UI only), Bing Webmaster Tools, www→apex 308 (Vercel → Domains; today 307), GitHub topics + licence split, Wayback save.

### Local development (verbatim, worked 2026-08-22)
- [REAL] Port 8000 is held by Docker — use 8010. Kill previous servers first (house rule).
  ```
  S=/private/tmp/claude-501/-Users-fcavalcanti-dev-esp-atlas/<session>/scratchpad   # any scratchpad dir
  python3 -m venv $S/venv && $S/venv/bin/pip install pytest jsonschema pyyaml httpx fastapi click uvicorn
  cd /Users/fcavalcanti/dev/esp-atlas
  PYTHONPATH=$PWD/apps/core/src:$PWD/apps/api/src:$PWD/apps/cli/src $S/venv/bin/python -m pytest apps/core/tests apps/api/tests apps/cli/tests -q
  PYTHONPATH=$PWD/apps/core/src:$PWD/apps/api/src ESP_ATLAS_DB_PATH=$S/esp-atlas-dev.db $S/venv/bin/uvicorn esp_atlas_api.main:app --port 8010 --log-level warning
  cd apps/web && npx next typegen && npx tsc --noEmit && npm run lint && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run build && NEXT_PUBLIC_API_URL=http://localhost:8010 npx next start -p 3000
  ```
  `NEXT_PUBLIC_*` is inlined at build time — rebuild before `next start` whenever it changes. Use the production build (not `next dev`) for screenshots: no dev badge, no compile delays.
- [REAL] Screenshots: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1800 --virtual-time-budget=8000 --screenshot=<out.png> <url>` wrapped in `timeout 60`. Dark mode: add `--force-dark-mode` (flips `prefers-color-scheme`; `next-themes` is `defaultTheme="system"`); assert with `--dump-dom | grep 'data-theme="dark"'`. Widths under ~500 px: a wrapper file `<iframe src="http://localhost:3000/…" style="width:390px;height:2300px;border:0">` shot at `--window-size=600,2300` (same for 768: iframe width 768 at window 900). **Never pass `--user-data-dir`** — it makes Chrome hang until killed (burned three times).
- [REAL] PSI via API needs a key (anonymous daily quota is shared and was exhausted); `gcloud services api-keys create --display-name=psi --api-target=service=pagespeedonline.googleapis.com --project esp-atlas-ga4` (Felipe's go was given for that today; delete after).

## Blocking constraints (builder: restate these before planning)

1. `main` is protected: PR only, `schema`+`tests` green, branch current with `main` (rebase), squash-merge with `gh` flipped to `fcavalcantirj` and back; never push to `main`.
2. Never delete or replace the Vercel glue: `apps/web/api/index.py`, `apps/web/vercel.json`, `apps/web/requirements.txt`, the `vercel-build` script in `apps/web/package.json`, `eslint.config.mjs`, `next.config.ts`. No Tailwind/shadcn/`@vercel/analytics`.
3. Thin client (`INTERFACE-SPEC.md` line 8): filtering, counting, ranking, derivation live in `esp_atlas_core` + FastAPI with tests; Next only fetches and renders. The `brand` hub needs the core filter first; SoC "parts on this chip" counts come from `/facets.soc_ref` (which includes the SoC itself + modules — label accordingly, never "boards").
4. `data/` is source-or-omit; no record edits without an official citation (Felipe's call); `price_tier` is editorial — never a spec, never `offers`/price in markup.
5. No secrets in the repo; SA/PSI keys live only in a scratchpad and are revoked/deleted after use; the GA measurement ID is public.
6. GA4 event and parameter names are contracts — add, never rename; new `origin` values ("browse", "brand") are fine (the `origin` dimension is registered); new parameters must be registered via the Admin API.
7. Polish is visual: no change to what the pages *contain* (no data logic, no new routes) — only how the restyle's system is applied; the palette and component tree stay.

## Accepted residuals / Refuted — don't fix

- `cd` inside a Bash call changes the session cwd; two commands failed today because a later `cd apps/web` ran from `apps/web`. Use absolute paths.
- Chrome headless `--user-data-dir` hangs (see above). The plain recipe returns in ~5 s.
- Next metadata merge: a page-level `openGraph`/`twitter` object replaces the root one wholesale — that is why F1 restates `siteName`/`url`/`images` on part pages and why F6 must remove those explicit `images` once the segment-local `opengraph-image.tsx` exists.
- `no-irregular-whitespace`: put ` `/` ` in regexes as escapes, never as literal characters (`components/JsonLd.tsx`).
- The 47/94 "missing metadata" crawl anomaly was a crawler artefact (head-only parsing + Next streaming metadata for non-bot UAs); Googlebot UA got blocking `<head>` metadata 64/64. Not a defect; the real note is the 3 s `TIMEOUT_MS` margin (0.13 s) — its change is Felipe's call (not chosen).
- `/compare` stays `noindex,follow` + client-rendered; curated "X vs Y" SSR pages are roadmap and which pairs exist is Felipe's call. 2-level `BreadcrumbList` is the default; the 3-level variant with a SoC link is a visible change = Felipe's call.
- `SearchAction` (retired rich result), `FAQPage` (no rich result outside government/health), cookie banner (decided no), `/ask` (not built), wizard ranking changes, `loading.tsx` on the part route, Composio OAuth — all refuted/decided; do not reopen.
- `SITE_EMOJI` unused export in `lib/site.ts` and `llmsTxtUrl()` unused after F3 — harmless, left on purpose.
- The GSC "Couldn't fetch" sitemap status is not ours to fix (see above).

## Hard rules & human-reserved decisions

- Commit messages: one-line conventional subject, optional body, trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`. Commit, push and open PRs freely for this work; merge each PR yourself once `schema`+`tests` are green and the branch is current (Felipe: auto-merge when green), then verify on production before starting the next.
- Polish PR first, then F4 → F5 → F6 (F4 and F6 edit `app/parts/[id]/page.tsx`; do them on branches from the freshly merged `main`, one at a time).
- iOS 16 px input floor, `TIMEOUT_MS`/error-path hardening, 3-level breadcrumb, `/api/` robots policy, render-path ISR on parts, any `next.config.ts` edit, any `data/` change, launch/visibility timing, Bing/GSC/Vercel dashboard settings, paid tools, newsletters/social — ARE FELIPE'S CALL; propose, do not implement.
- PR-F7 (`@vercel/speed-insights`) — Felipe did **not** answer; ask once, in the plan's questions; do not add the dependency without a yes.
- Visible design changes beyond applying the restyle's own tokens consistently are NOT wanted; when a polish fix needs a judgment call (e.g. how the chip chain should stack on phones), show before/after screenshots and ask.

## Acceptance checklist (the author approves the plan ONLY against these)

1. The plan restates all seven blocking constraints in its own words, first.
2. `[REAL]` claims re-verified and discrepancies listed: `main` head and merged PR list, open PRs and their CI state, F1/F2/F3 facts on production (canonical, `noindex, follow`, `application/ld+json` count, `/llms.txt` 200, sitemap `<lastmod>` count), the CSS line numbers above still match.
3. A **polish sweep matrix** is defined before any fix: routes `/`, `/compare` (empty and with 3 ids), `/parts/<board>` (`adafruit-feather-esp32-s3`), `/parts/<soc>` (`esp32-s3` — 33 related; `esp32-c5` — none), `/parts/<module>` (`esp32-c6-wroom-1`), 404 (`/parts/nope`), the `PartDetailClient` loading state if reproducible × widths 390 / 768 / 1024 / 1440 × light / dark, each screenshot listed by path; findings tagged with the CSS rule and line that causes them.
4. The polish plan names the fix for each known issue and keeps the restyle's system: (a) remove inner scrolling on `.part-aside` and `.compare-picker` (no `max-height`/`overflow-y` scroll containers; sticky only where the content fits, otherwise static) — Felipe's "scroll without the need of scroll"; (b) compare clipping (`minmax(0, 1fr)` + `min-width: 0`) and the CLS skeleton for the Suspense fallback; (c) chip chain on narrow widths (chips shrink/stack without a lonely arrow; current chip not full-width with the badge pushed away); (d) mobile gutter (`--page-x` override below 600 px so footer matches header/main); (e) `.segmented` not stretched; (f) anything the sweep finds, with before/after screenshots; (g) no pixel change on desktop where nothing was wrong. Verification = the same matrix re-shot plus PSI CLS < 0.1 on `/compare` (mobile and desktop) after merge.
5. F4 plan: `export const revalidate = 300` on `app/page.tsx` (ISR, not `force-dynamic`) + never-throwing `fetchFacets()` in `lib/api-server.ts`; "Browse by chip" with 11 SoC links labelled "N parts on this chip"; SoC page main-column `<h2>Boards and modules on {name} ({n})</h2>` rendered only when n > 0 + `ItemList` JSON-LD added to `lib/structured-data.ts`; `result_click` with `origin: "browse"` added to the `ResultOrigin` union in `lib/analytics.ts`; "Browse by brand" only after F5; verification = re-crawl: 0 orphans, 0 unreachable, depth ≤ 2 for all 96 URLs.
6. F5 plan: core first — `apps/core/src/esp_atlas_core/search.py` `_EXACT_FILTERS` + `parts.vendor_or_brand = ?`; `apps/api/src/esp_atlas_api/main.py` `/search?brand=`; CLI `--brand`; tests in `apps/core/tests/test_search.py`, `apps/api/tests/test_app.py`, `apps/cli/tests/test_cli.py` mirroring the existing `form`/`soc` filter tests; then `app/brands/page.tsx` (index from `/facets.vendor_or_brand`) + `app/brands/[brand]/page.tsx` (SSR, `generateMetadata`, canonical, JSON-LD `CollectionPage`/`ItemList`), sitemap entries, footer "Explore" link to `/brands` (not 11 links). Route slug = folder name (`unexpected-maker`). Verification = pytest green in all three suites + `/api/search?brand=adafruit` → 11 + sitemap 108 URLs.
7. F6 plan: `app/parts/[id]/opengraph-image.tsx` with `next/og` `ImageResponse` (`params` is a Promise in Next 16): name, brand, SoC, up to 3 spec chips, **no price**; remove the explicit `images` entries F1 added for part pages; verification = distinct 1200×630 PNG per part (spot-check 5), `og:image` points at it.
8. Order and gating: polish PR → F4 → F5 → F6 → (F7 only on Felipe's yes) → final docs PR updating §13 table A statuses; each PR auto-merged when green and current, production verified after each.
9. The plan ends with `## Concerns` (HIGH/MEDIUM/LOW) and `## Questions for the author`, and answers the open questions below.

## next_action

After APPROVED: `git fetch origin && git checkout -b polish/editorial-consistency origin/main`, start the API on 8010 and a production build on 3000 (recipe above), shoot the full polish matrix (checklist 3) into a scratchpad, write the findings list with CSS line references, then fix in `apps/web/app/globals.css` (+ `app/compare/page.tsx` for the skeleton), re-shoot, open the polish PR with before/after paths in the body.

## Open questions

1. Speed Insights (PR-F7): Felipe did not answer — ask once; default is **no**.
2. Chip chain on phones: stack vertically (chip / arrow / chip, each full width) or shrink chips inline (badge stays next to the name)? Recommend one with screenshots.
3. Sticky aside: keep `position: sticky` when the aside is shorter than the viewport and fall back to static when taller (pure CSS cannot know the height — JS or always-static), or always static? Recommend always static unless a no-JS sticky works without an inner scrollbar.

## Pointers

- Repo `/Users/fcavalcanti/dev/esp-atlas` (start on `main`; run `git pull` first). Docs: `docs/seo-audit/2026-08-22.md` (§13 = backlog), `docs/handovers/2026-08-22-seo-audit-and-restyle/` (round-1 handover, plan, review — decisions and the six original constraints), `PROJECT_KNOWLEDGE.md` (untracked, repo root), `apps/web/README.md` (analytics taxonomy), `AGENTS.md`, `INTERFACE-SPEC.md`, `SPEC.md`.
- Production https://esp-atlas.com · repo https://github.com/fcavalcantirj/esp-atlas · PRs #3–#7 for the conventions used (bodies list verification steps).
- Google: GA4 `properties/551132215`; GCP `esp-atlas-ga4`; SA `esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com` (no key exists; Felipe mints on request, revoke after). GSC property `sc-domain:esp-atlas.com` (SA Restricted).
- Secrets: none in the repo; `.env*` gitignored; Vercel env in the dashboard (project `flowcoders/esp-atlas`, not reachable from this machine's Vercel CLI).
