---
round: 1
builder_session: fresh session 2026-08-22 (~16:00 UTC), plan mode; re-verified HANDOVER.md @ f0262ca read-only against prod, repo, gh, gcloud, the design zip
---

# Plan r1 — editorial restyle + SEO/growth/analytics audit of esp-atlas.com

## Blocking constraints, restated

1. **`main` is locked.** Every change lands through a PR whose `schema` and `tests` checks are green and whose branch is current with `main` (`strict: true`); `enforce_admins` is on, so nobody bypasses. Never `git push origin main`. Squash-merge (`gh pr merge N --squash --delete-branch`). `gh` must be flipped to `fcavalcantirj` for `pr create` / `pr merge` / repo-settings calls and flipped back to `fcavalcanti-onvida` right after; SSH pushes are already `fcavalcantirj`.
2. **The Vercel glue is never deleted or replaced.** `apps/web/api/index.py`, `apps/web/vercel.json`, `apps/web/requirements.txt`, the `vercel-build` script in `apps/web/package.json`, `eslint.config.mjs`, `next.config.ts` stay in place and keep doing what they do. The zip's `package.json` (adds Tailwind/shadcn/`@vercel/analytics`, removes `eslint` + `lint` + `vercel-build`), `next.config.mjs`, `postcss.config.mjs` and the Tailwind/shadcn dependencies never enter the repo — they would delete the Python-function bundling step and the lint gate. (This plan touches none of these files.)
3. **Thin client.** Filtering, ranking, counting and any derivation live in `esp_atlas_core` and are exposed by FastAPI; Next.js only fetches and renders. SEO pages that need data use `/facets`, `/search?soc=&type=`, `/parts`, `/parts/{id}` as they are, or first add a core function + API route + tests (e.g. a `brand` filter), never compute in the web app.
4. **Data is source-or-omit.** The audit never adds or edits `data/` records without an official citation. `price_tier` is an editorial bucket — never rendered or marked up as a spec (so no `offers`/price in any JSON-LD).
5. **No secrets in the repo.** The GA measurement ID is public. Service-account keys live only in the session scratchpad and are revoked after use. The Composio API key that surfaced in an earlier chat is never reused and never written anywhere (rotating it is Felipe's call; the plan does not touch Composio).
6. **GA4 names are contracts.** Event and parameter names in `lib/analytics.ts` map to registered custom definitions; renaming silently breaks reports. Add new events/params instead, and register new params through the Admin API (service account) when adding them.

## Handover discrepancies

Checked this session (2026-08-22 ~15:30–16:00 UTC) and found **clean**: `origin/main` = `589ef35`; all production curls (`/api/health` count 94, `/api/facets` 200, `/api/parts/xiao-esp32c6` chain.soc.id `esp32-c6` + 6 related, `/api/search?soc=esp32-h2&type=board` → `esp32-h2-devkitm-1`, `/parts/m5stack-cores3` `<title>` + description, `/parts/nope` 404, sitemap 96 `<loc>`, robots text, GA tag `G-66L7SDXKJZ`, classes `home-layout home-sidebar site-footer-grid`); branch protection via owner token (`["schema","tests"]`, strict, 0 reviews, `enforce_admins: true`); `has_discussions: true`; PRs #1/#2 merged; `gh` keyring = `fcavalcanti-onvida` (active) + `fcavalcantirj`; `ssh -T git@github.com` → `fcavalcantirj`; `.github/workflows/validate.yml` jobs as described; repo layout, `lib/api-server.ts`, `lib/site.ts`, `lib/analytics.ts`, `app/sitemap.ts`, `app/robots.ts`, `next.config.ts`, `vercel.json`, `package.json` as described; no `loading.tsx` under `app/parts/[id]/`; data 11/6/77; `PROJECT_KNOWLEDGE.md` untracked at root; 180 `def test_` functions counted (suite **not re-run** — plan mode); port 8000 held by `com.docker`; zip: the 8 differing files and their diffs match the handover, `app/parts/[id]/page.tsx` identical, colour tokens identical, zero Tailwind directives, zip-only scaffolding list correct, deploy-critical files absent from the zip; GCP: SA `esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com` exists with **zero** user-managed keys, enabled APIs = `analyticsadmin`, `analyticshub`, `iam`, `iamcredentials` (no `analyticsdata`, `searchconsole`, `pagespeedonline`); Vercel CLI = `fcavalcanti-onvida`, scope `flowcoders` "does not exist" for it.

Discrepancies / additions (none blocking):

1. **Citation wording.** "Smart API, dumb client" is not a literal phrase in `INTERFACE-SPEC.md`; line 8 says the website, CLI, MCP tool and bots are "thin front-ends over it". Same principle; constraint 3 stands.
2. **Zip `public/` also carries icons**, not only placeholders: `apple-icon.png`, `icon-dark-32x32.png`, `icon-light-32x32.png`, `icon.svg`. Not taken (`app/icon.svg` stays, per the handover).
3. **`.site-logo-text` has no selector** in the zip's `globals.css` (nor in the repo's). Harmless — it inherits `.site-logo`. The "every className has a selector" claim is off by this one.
4. **Zip `HeaderControls.tsx` drops the pre-mount `◐` glyph.** `isDark = mounted && resolvedTheme === "dark"`, so SSR/first paint always shows the moon and dark-mode users see it flip to the sun after hydration. No hydration error, a cosmetic flicker. See Q7.
5. **PageSpeed Insights anonymous quota is exhausted today** (`Queries per day` on Google's shared consumer project `583797351490`). CWV/Lighthouse collection needs an API key on `esp-atlas-ga4` (step B0).
6. **Not re-verifiable from here**: the GA4 custom-definition list (needs an SA key). Accepted as author-verified; the code-side half of the comparison was done now (see §7 below).
7. **Docs-only PRs cannot go green.** `validate.yml` triggers on `pull_request.paths: ["data/**","schema/**","scripts/**","apps/**"]`. A PR touching only `docs/` starts no workflow, the required `schema`/`tests` contexts stay "Expected", and with `enforce_admins: true` the merge button is dead. This hits the audit-doc PR **and** the handover branch itself (no PR open for it yet). See Concerns + Q4.

Baseline facts gathered for the audit (not contradictions): no JSON-LD on any page; `/` has no `<link rel="canonical">`; part pages' `twitter:title`/`twitter:description` are inherited from the root layout (the `og:` pair is correct); `/compare?ids=…` has neither canonical nor `robots` meta; `/opengraph-image` and `/llms.txt` are 404 (the footer's llms.txt link points at the GitHub blob); `www.` → 307 to apex, `http://` → 308, trailing slash → 308 strip; HSTS `max-age=63072000` (no preload); zero `<img>` on part pages; footer renders four `<h2>` on every page; `/search` has **no `brand` filter** (`_EXACT_FILTERS = {"type","form","soc","module"}`); `get_part().related` is **uncapped** — a SoC page already lists every board/module on the chip as SSR links; `/parts` returns `sources[].verified` for every record; home SSR links to parts = 3 (footer: ESP32-C6/S3/H2); `HomeView` reads no URL params.

## Acceptance checklist — point-by-point

1. Six constraints restated above, first section, own words → satisfied.
2. Restyle copies exactly `app/globals.css`, `app/layout.tsx`, `components/SiteHeader.tsx`, `components/SiteFooter.tsx`, `components/PartResultCard.tsx`, `components/HeaderControls.tsx` (A3). Keeps `lib/api.ts`, `package.json`/`package-lock.json` (Newsreader comes from `next/font/google`, already a dependency of `next`), `eslint.config.mjs`, `vercel-build`, `next.config.ts`, `apps/web/api/**`; takes none of `components.json`, `components/ui/`, `lib/utils.ts`, `next.config.mjs`, `postcss.config.mjs`, `pnpm-lock.yaml`, `esp-atlas.db`, `public/**` (A4) → satisfied.
3. Verification chain `npx next typegen && npx tsc --noEmit && npm run lint && npm run build`; 12 screenshots (3 routes × 1440/390 × light/dark) before the PR; post-merge prod curls (A6–A10) → satisfied.
4. Evidence source per audit section and how it is obtained (B1 table); sections without data are marked as limitations with the cheapest path → satisfied.
5. Audit at `docs/seo-audit/2026-08-22.md`, 13 sections in order, every bullet addressed or `N/A — <why>`, Critical/High/Medium/Low tags, effort-vs-impact matrix, "ship now (0–30 d)" separated from roadmap (B2) → satisfied.
6. Each required technical decision is made below with file paths (C1–C13, including "top parts" in C4), all data via existing or newly added API → satisfied.
7. Key events, GSC↔GA4 link, UTM convention, Vercel Analytics/Speed Insights yes/no, dims-vs-code check (§7) → satisfied.
8. Order: PR-A restyle → PR-0 (CI trigger; opened after Q4, merged before PR-B — the only way a docs-only PR can go green) → PR-B audit doc → PR-F1…F7 one concern each; each green; each merged only on Felipe's go → satisfied.
9. `## Concerns` with severities and `## Questions for the author` including answers to the three open questions (Q1–Q3) → satisfied.

## The plan

### Phase A — restyle PR (`restyle/editorial-newsreader`)

A1. `git fetch origin && git checkout -b restyle/editorial-newsreader origin/main`.
A2. `unzip -q -o /Users/fcavalcanti/Downloads/esp-atlas.zip -d <scratchpad>/design-zip` (scratchpad only).
A3. Copy exactly six files into `apps/web/`:
    `app/globals.css`, `app/layout.tsx`, `components/SiteHeader.tsx`, `components/SiteFooter.tsx`, `components/PartResultCard.tsx`, `components/HeaderControls.tsx`.
    `git status` must show exactly these six modified, nothing added.
A4. Not copied: `lib/api.ts` (zip drops the `http://localhost:8000` dev fallback), `package.json`, every zip-only file. `SITE_EMOJI` stays exported from `lib/site.ts` (unused after this; zip keeps `lib/site.ts` byte-identical) — see Q9.
A5. "Finish" pass, only where the zip is inconsistent: nothing found except discrepancy 4 (header icon) — decision deferred to Q7; no other visual changes.
A6. Static checks: `cd apps/web && npx next typegen && npx tsc --noEmit && npm run lint && npm run build` (expect `/` and `/compare` static, `/parts/[id]` and `/sitemap.xml` dynamic, Newsreader + Geist Mono woff2 emitted, no Geist Sans).
A7. Local run (kill previous `uvicorn`/`next dev` first): scratchpad venv recipe from the handover, API on **8010** (8000 is Docker's), `NEXT_PUBLIC_API_URL=http://localhost:8010 npm run dev`.
A8. Screenshots (12): `/`, `/parts/xiao-esp32c6`, `/compare?ids=esp32-c6,esp32-h2,xiao-esp32c6` × 1440 px (headless Chrome recipe verbatim from the handover) × 390 px (iframe wrapper at `--window-size=600,2300`) × light/dark. Dark: the provider is `next-themes` `defaultTheme="system" enableSystem`; adding `--force-dark-mode` to the same Chrome command flips `prefers-color-scheme: dark` → `<html data-theme="dark">` — **verified on this Mac against prod** (`--dump-dom` shows `data-theme="dark"` with the flag, light without). Still assert it per run with `--dump-dom | grep 'data-theme="dark"'` before trusting the PNG. PNG paths are listed in chat for Felipe to open (GitHub image upload is UI-only).
A9. Commit `feat(web): editorial restyle — Newsreader serif, geometric tokens, flat header` (+ `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`), push, `gh auth switch --user fcavalcantirj && gh pr create --base main --title … --body …` (body: the six files, what was deliberately not taken, screenshot list), `gh auth switch --user fcavalcanti-onvida`.
A10. After Felipe's go: `gh pr merge N --squash --delete-branch` (flip `gh` both ways). Prod checks: `<title>` on `/parts/m5stack-cores3`, `/parts/nope` → 404, sitemap `<loc>` count 96, GA tag present, Newsreader woff2 referenced in `/` HTML, `.site-logo-mark` absent, `.footer-standfirst` present.

### Phase B — audit doc PR (`docs/seo-audit-2026-08-22`)

B0. Prerequisites (Felipe or, with his go, me via the logged-in `gcloud` account `felipe.cavalcanti.rj@gmail.com`):
    - `gcloud services enable analyticsdata.googleapis.com searchconsole.googleapis.com pagespeedonline.googleapis.com --project esp-atlas-ga4`
    - PSI key: `gcloud services api-keys create --display-name=psi-audit --api-target=service=pagespeedonline.googleapis.com --project esp-atlas-ga4` (scratchpad only; delete after)
    - SA key: handover command verbatim (`gcloud iam service-accounts keys create <scratchpad>/ga4-sa.json …`); revoke + delete after use.
    - Felipe adds the SA email as a user (Restricted is enough) on the GSC property `esp-atlas.com`.
B1. Evidence, all saved under `<scratchpad>/audit/` (raw JSON/HTML kept for the review, never committed):

    | Spec section | Evidence | How |
    |---|---|---|
    | 1 Exec summary | derived from all below | — |
    | 2 Technical/rendering | curl of all 96 sitemap URLs (SSR HTML) + headless Chrome `--dump-dom` of `/`, a part, compare (post-JS) → diff SSR vs rendered; redirect matrix (apex/www/http/trailing slash — captured); robots/sitemap/canonical/JSON-LD extraction; PSI mobile+desktop for `/`, `/parts/xiao-esp32c6`, `/compare?ids=esp32-c6,esp32-h2,xiao-esp32c6` (LCP/CLS/TBT/INP-if-CrUX, Lighthouse SEO); GSC **Performance API** (`searchanalytics.query`, last 28 d, by page/query/device) + `sitemaps.get` + URL Inspection API for 5 URLs | curl, Chrome, PSI API key, GSC API via SA |
    | 3 On-page | title/description/OG/Twitter/H1–H3/alt/breadcrumb per page from the crawl; internal-link graph (in-degree per URL, orphans = in sitemap with 0 SSR inbound) | crawl + small Python script |
    | 4 Content/programmatic | record counts by type/brand/SoC from `/facets`; template analysis of part pages; gap list vs `COVERAGE.md`; query ideas from GSC (sparse) + WebSearch sampling | API, repo, WebSearch |
    | 5 Off-page | GSC Links report (manual export — API has no links endpoint), `"esp-atlas"` / `site:` WebSearch; **limitation**: no Ahrefs/Semrush — cheapest path named (Ahrefs Webmaster Tools free tier, needs GSC verification) | WebSearch, GSC UI |
    | 6 Analytics | GA4 Admin API: data stream, enhanced measurement, custom definitions, key events; GA4 Data API `runReport` events since launch; code taxonomy diff (§7); no GTM container exists → N/A | SA key |
    | 7 UX/engagement | GA4 Data API (engagement, scroll, device) — site is ~1 day old → baseline only, trends N/A | SA key |
    | 8 Local/intl | N/A (no business location, English-only) — hreflang decision documented | reasoning |
    | 9 Competitive | 4–6 competitors picked by WebSearch for ~15 head/long-tail queries ("esp32 board comparison", "esp32-c6 vs h2", "xiao esp32c6 specs"…); share of voice = own impressions per query from `searchanalytics.query` + manual SERP sampling of those 15 queries + Google Trends for relative interest; **limitation** stated, cheapest upgrade = Ahrefs Webmaster Tools free tier (needs GSC verification) for competitor keyword/backlink overlap | WebSearch, GSC API |
    | 10 Risks | from crawl (doorway/thin/duplicate), code (cloaking none), CWV | crawl |
    | 11 KPIs | GSC Performance API (`searchanalytics.query`: clicks/impressions/CTR/position) + GA4 Data API baselines; proposed dashboard (Looker Studio free) | SA data |
    | 12 Experiments | ranked list, hypotheses, instrumentation (new GA4 events) | reasoning |
    | 13 Roadmap | 0–30 / 30–60 / 60–180 / 6m+ with owners | reasoning |

B2. Write `docs/seo-audit/2026-08-22.md`: 13 sections in the spec's order, every bullet answered or `N/A — <why>`; `[Critical]/[High]/[Medium]/[Low]` on each finding; effort-vs-impact matrix (table, 2×2 quadrants); "Ship now (0–30 d, PR list)" separated from roadmap; "Data limitations" subsection per section; doc-drift note on `ARCHITECTURE.md`/`SPEC.md`. Screenshots: ≤6 PNGs ≤300 KB under `docs/seo-audit/assets/2026-08-22/` (Q6).
B3. PR `docs(seo): technical SEO, growth and analytics audit 2026-08-22` — needs PR-0 first (Q4).

### Phase C — fix PRs (0–30 days, one concern each, in this order)

Decisions for every item in checklist 6, with files:

C1. **Metadata hygiene — PR-F1 `fix(seo): canonicals, compare indexing, twitter cards, static OG image`.**
    - `app/page.tsx`: export `metadata` with `alternates: { canonical: "/" }`.
    - `app/compare/page.tsx`: `alternates: { canonical: "/compare" }` + `robots: { index: false, follow: true }` (Q2 answer: the page is a client-only tool; every `?ids=` variant renders the same shell → `noindex` + canonical; curated "X vs Y" landing pages become a separate SSR route on the roadmap, content is Felipe's call).
    - `app/parts/[id]/page.tsx` `generateMetadata`: add `twitter: { card: "summary_large_image", title, description, images: [...] }` (fixes the inherited root title) and extend `openGraph` with `siteName: SITE_NAME`, `url: "/parts/<id>"`, `images: [...]`. Reason: Next's merge rule replaces a nested `openGraph`/`twitter` object wholesale with the last segment's — that is why part pages today lack `og:site_name`/`og:url`, and why a root static image would **not** propagate to part pages on its own (verified against `next/dist/lib/metadata/resolve-metadata.js`). Until F6 lands, `images` points at the static root image.
    - `app/opengraph-image.png` (1200×630 static, brand + tagline) → `og:image`/`twitter:image` on `/`, `/compare`, 404; `/opengraph-image` stops 404ing. Root `twitter.card` → `summary_large_image`.
    - www → apex is a **307** from Vercel: recommend 308 in Vercel → Domains (dashboard, Felipe).
C2. **JSON-LD — PR-F2 `feat(seo): JSON-LD for site, dataset and part pages`.**
    - New server component `components/JsonLd.tsx` (`<script type="application/ld+json">`, `JSON.stringify` with `<` escaped).
    - `/`: `WebSite` (+ `Organization` publisher) **without `SearchAction`** — Google retired the sitelinks search box (announced 2024-10-21, removed from results 2024-11-21; verified on the Search Central blog this session) and `/` accepts no `?q=`; adding URL-driven search for retired markup is not worth it. Plus one `Dataset` (name, description, license CC-BY-SA 4.0, `distribution` → `https://github.com/fcavalcantirj/esp-atlas/tree/main/data` and `https://esp-atlas.com/api/parts`, `isAccessibleForFree`).
    - `/parts/[id]`: `TechArticle` (headline = name, `about` → nested `Product` with only `name`, `brand`/`manufacturer`, `model`, `category` — **no `offers`, no price, no rating**, constraint 4), `citation` → each `sources[].url`, `dateModified` = max `sources[].verified`, `isPartOf` WebSite) + `BreadcrumbList`. Why not top-level `Product`: the site is explicitly "not a shop" (`SPEC.md` anti-goals), a `Product` without offers/reviews earns no rich result and collects "missing field" warnings; `Dataset` fits the corpus, not one page; `TechArticle` matches "cited technical reference page". Rendered only on the SSR path (data from `fetchPartDetail`, no new API).
    - `BreadcrumbList` must mirror the visible crumb (Google guideline). Today the middle crumb ("Boards") is an unlinked `<span>` — a `ListItem` without `item` URL is only allowed last, so the default is a **2-level** list (Home › part) with **no visible change** (hard rule: no visuals beyond the zip). Alternative, gated by **Q5**: make the middle crumb the SoC page link (`chain.soc`) in `PartHeader.tsx` and emit 3 levels — better internal linking, but a visible change.
C3. **Sitemap + llms.txt — PR-F3 `fix(seo): sitemap lastModified, serve /llms.txt`.**
    - `app/sitemap.ts`: `lastModified` = max `sources[].verified` per part (already in `/parts` payload; no core change); static routes get the global max.
    - `app/llms.txt/route.ts` with `export const dynamic = "force-static"`: the handler runs at **build time** (when `../../llms.txt` is reachable — the existing `vercel-build` already `cp -r ../../data` from the same parent) and ships as static output; every merge to `main` redeploys, so it never goes stale. `next.config.ts` stays byte-identical; no tracing config needed. Verify `/llms.txt` is listed as static (○) in the `next build` output and returns 200 on the preview. Footer `llmsTxtUrl()` → `/llms.txt` (keep the GitHub `link_type` `llms_txt`; constraint 6 untouched). Fallback only if the build-time read fails on Vercel: committed copy at `apps/web/public/llms.txt` + a `scripts/` diff check in CI.
C4. **Crawlable home + SoC hub — PR-F4 `feat(seo): server-rendered browse links on home, SoC page as hub`.**
    - `app/page.tsx` becomes `dynamic = "force-dynamic"` (same pattern as `sitemap.ts`; `next build` cannot reach the API; one fetch, cached 1 h, 3 s timeout, never throws — gated by **Q11** because `/` is static today) and server-fetches `/facets` (`soc_ref`, `vendor_or_brand` with counts) via a new `fetchFacets()` in `lib/api-server.ts`; on error the section is omitted. Renders `Browse by chip` (11 SoC pages, labelled "N parts on this chip" — the `soc_ref` facet counts the SoC itself + modules + boards, so it is not a board count; a true board count needs a type-scoped facet in core + API + tests, proposed inside F5) and `Browse by brand` (11 links to `/brands/<brand>` once F5 ships; omitted until then). Fixes "home results are client-only".
    - **Top parts on `/`: N/A for now** — core has no popularity signal and every part is at depth 2 via its SoC hub; the footer keeps its 3 SoC links. Roadmap: a "featured parts" block fed by GA4 `part_view` top-10 after 30 days of data, or a curated list — which one IS FELIPE'S CALL.
    - `/parts/<soc>`: promote the uncapped `related` list from the aside `<h3>` into a main-column `<h2>Boards and modules on {name} ({n})</h2>` with an `ItemList` JSON-LD — the SoC page **is** the SoC hub (Q3 answer: no new `/socs/*` route → no duplicate content, crawl depth 2, zero new API).
C5. **Brand hubs — PR-F5 `feat(search): brand filter; web /brands and /brands/[brand]`** (core + API + tests first, constraint 3):
    - `apps/core/src/esp_atlas_core/search.py`: add `"brand"` to `_EXACT_FILTERS`, clause `parts.vendor_or_brand = ?`; `apps/api/src/esp_atlas_api/main.py`: `brand: Optional[str]` on `/search`; `apps/cli`: `--brand`; tests in `apps/core/tests/test_search.py`, `apps/api/tests/test_app.py`, `apps/cli/tests/test_cli.py` (follow `test_search_structured_filter_form_factor`).
    - `apps/web/app/brands/page.tsx` (index from `/facets.vendor_or_brand`) + `apps/web/app/brands/[brand]/page.tsx` (SSR, `generateMetadata`, list via `/search?brand=`), both `force-dynamic` + 1 h fetch cache; add to `sitemap.ts` and footer Explore. Route naming: `/brands/<folder-slug>` (e.g. `unexpected-maker`).
C6. **Per-part OG image — PR-F6 `feat(seo): per-part opengraph-image via next/og`** (`app/parts/[id]/opengraph-image.tsx`, `ImageResponse`, `params` is a Promise in Next 16; name/brand/SoC/3 spec chips; no price). A segment-local image file merges after the page's own `openGraph` (verified with Next's `accumulateMetadata`), so F6 also removes the explicit `images` entries added in F1. Quick win, after F1.
C7. **Analytics — no-code actions via the SA + Admin API** (see §7) and **optional** PR-F7 `feat(web): Vercel Speed Insights` (adds `@vercel/speed-insights`, a dependency — Felipe's go).
C8. Images/alt: no `<img>` anywhere; only the OG images above. Vendor product photos need licensing → roadmap, Felipe's call.
C9. H1: unique per page already (home tagline, part name, "Compare"); footer's four `<h2>` per page noted as Low (outline noise) — changed to `<p className="footer-title">` in F1 **only if Q10 is answered yes** (default: no change).
C10. Thin content (94 templated pages): mitigated by C2/C4 (unique `TechArticle` + hub context + breadcrumb); remaining risk logged Medium; richer record prose is data (Felipe's call).
C11. Canonical/trailing slash: consistent (308 strip) — no change beyond C1.
C12. `/api/docs` is disallowed by robots and linked from the footer — fine, noted.
C13. HSTS preload: Low, not proposed.

### §7 Analytics decisions (checklist 7)

- **Key events**: mark `result_click` and `outbound_click` (Admin API `keyEvents.create`, counting method ONCE_PER_EVENT). `wizard_submit`: **no** — it is an input, not an outcome; the funnel is `wizard_submit → wizard_results (result_count>0) → result_click(origin=wizard)`. Secondary candidate: `compare_view`.
- **GSC ↔ GA4 link**: UI-only — the GA4 Admin API (v1alpha/v1beta) has no Search Console link resource (checked this session). GA4 Admin → Product links → Search Console links, done by Felipe (needs GSC owner).
- **UTM convention**: do **not** add UTMs to outbound GitHub links (GitHub shows referrer domains only; `outbound_click` already captures `link_type`). Define inbound UTMs for links Felipe posts, when and if he announces the site (visibility IS FELIPE'S CALL): `utm_source=<github|reddit|hn|discord|x>`, `utm_medium=<readme|social|community|referral>`, `utm_campaign=<name Felipe picks, e.g. contribute>`, `utm_content=<placement>`; README/Discussions links get `utm_source=github&utm_medium=readme`.
- **Vercel Analytics: no** (duplicates GA4 page views, second script). **Speed Insights: yes, if the Vercel plan includes it** — field CWV before CrUX has enough traffic (PR-F7, Felipe's go).
- **Custom dims vs code**: params emitted by `track()` calls but **absent** from the registered list: `brand`, `soc_ref` (part_view), `from_id`, `to_id` (chain_click), `endpoint`, `status` (api_error), `path` (not_found), `panel`, `open` (advanced_filters_toggle), `direction` (font_size_change), `count` (compare_view; metric), plus README-listed `ieee802154`, `usb_native`, `has_query`, `url`. Recommend registering all but `url` (high-cardinality, >100 chars) as dimensions (GA4 allows 50 event-scoped; 20 used) and `count` as a metric; `url` stays unregistered by design. Re-diffed against the live list once the SA key exists.

### Preliminary effort-vs-impact (final matrix in the audit)

| | Low effort | High effort |
|---|---|---|
| **High impact** | F1 canonical/noindex/twitter/OG (1 PR), F3 lastModified+llms.txt, C2 JSON-LD, F4 home links | F5 brand hubs (core+api+web), curated comparisons (roadmap) |
| **Low impact** | HSTS preload, footer headings, www 307→308 | product photos, i18n |

## Concerns

- [HIGH] **Docs-only PRs are un-mergeable** under the current protection (`paths:` filter + `enforce_admins`; GitHub's own docs: path-skipped required checks stay Pending and block merging, and the recommended fix is to not require skippable workflows). Fix = PR-0 `ci: run validate on every pull request` — **drop the `paths:` block** (pushes to `main` unchanged). Only this variant self-validates: PR-0 touches just `.github/workflows/validate.yml`, so "add `docs/**` to the list" would leave PR-0 itself stuck. A CI edit not in the handover → waits for Q4. Without it the audit-doc PR and the handover branch cannot land.
- [HIGH] **PSI quota** — zero CWV/Lighthouse data until an API key exists on `esp-atlas-ga4` (B0). Needs a GCP write (Felipe or me-with-go, Q8).
- [MEDIUM] **GSC data depends on Felipe** adding the SA to the property; historical trends are N/A anyway (live on production since 2026-08-22), so sections 2/6/7/11 are baselines, stated as such.
- [MEDIUM] **Metadata merge semantics** (found by verification): part pages' `generateMetadata` replaces the root `openGraph`/`twitter` objects wholesale, so root-level images/siteName/url never reach them. F1 sets `images`, `siteName`, `url` explicitly on part pages; F6 swaps in the segment-local per-part image.
- [MEDIUM] **Font swap / type-scale CLS** on part pages (Newsreader `display: "swap"`, 15 px base, `clamp()` h1). `next/font/google` applies `adjustFontFallback` by default (size-adjusted fallback, verified in the installed 16.3.2), so the expectation is low CLS; measured post-merge with PSI since pre-merge previews are behind Vercel login and PSI quota is gone today.
- [MEDIUM] **`/` becomes dynamic** in F4 (static today). Same pattern as `sitemap.ts`, 1 h fetch cache, 3 s timeout, never throws; cold Python function → section omitted, never a 500. Gated by Q11.
- [LOW] Header icon flicker in dark mode (discrepancy 4); `SITE_EMOJI` unused export; `.site-logo-text` without selector — cosmetic, Q7/Q9.
- [LOW] `SearchAction` deliberately omitted (retired rich result, verified); trivial to add later if `/` gains `?q=`.
- [LOW] `/llms.txt` via `force-static` route depends on `../../llms.txt` being readable at build time on Vercel — same parent access `vercel-build` already relies on; confirmed by the preview's 200 before merge.

## Questions for the author

1. **(Open Q1 — fonts)** Confirmed: both faces load only via `next/font/google` (`Newsreader` with `style: ["normal","italic"]`, `display: "swap"`; `Geist_Mono` unchanged) — no package added. CLS cannot be measured before merge (PSI quota exhausted, previews gated); plan measures right after merge and, if CLS > 0.1 on part pages, follows up with `display: "optional"` or explicit `adjustFontFallback`. OK to ship on that basis?
2. **(Open Q2 — compare)** Recommendation: `noindex,follow` + canonical `/compare` for all `?ids=` variants now; curated comparisons ("ESP32-C6 vs ESP32-H2") as a **separate SSR route** on the roadmap, because the current page has no crawlable content and each `?ids=` permutation is a duplicate shell. Agree?
3. **(Open Q3 — hubs)** Recommendation: SoC hub = enrich the existing `/parts/<soc>` page (C4; `related` is already uncapped and SSR, so zero duplicate content and no new data path); brand hub = new `/brands/<brand>` backed by a new core/API `brand` filter (C5, core+API+tests first). Is the core/API change in scope for the 0–30 d fix PRs?
4. May I open **PR-0** that removes the `paths:` block from `validate.yml` so every PR (docs-only included) runs the required checks? It is the only self-validating variant (adding `docs/**` would leave PR-0 itself stuck). Without it neither the audit PR nor the handover branch can merge.
5. Breadcrumb (C2): keep the visible crumb as-is and emit a 2-level `BreadcrumbList` (default, no visual change), or turn the middle crumb into the SoC-page link and emit 3 levels (a visible change beyond the zip, better internal linking)?
6. Audit screenshots: commit ≤6 small PNGs under `docs/seo-audit/assets/2026-08-22/`, or keep them out of the repo and reference scratchpad paths in chat?
7. Header theme icon: take the zip as-is (moon-then-sun flicker for dark-mode users) or keep the repo's `mounted` gate with the zip's SVGs (3-line "finish" edit)?
8. GCP writes in B0 (enable 3 APIs, create a PSI API key): me via the logged-in `gcloud` account after your go, or you?
9. Remove the now-unused `SITE_EMOJI` export from `lib/site.ts` in the restyle PR, or leave it (zip keeps `lib/site.ts` identical)? Default: leave.
10. Footer `<h2>` → `<p className="footer-title">` in F1 (heading-outline hygiene, no visual change)? Default: **no change** unless you say yes.
11. `/` turning `force-dynamic` in F4 (one cached `/facets` fetch per request, section omitted on API failure) — acceptable, or keep `/` static and put the browse links only on `/brands`, the SoC pages and the footer?
