---
slug: seo-audit-and-restyle
date: 2026-08-22
status: approved        # open → in_review → approved | escalated
round: 1
author_session: prod-polish session that shipped PR #2 (589ef35) to esp-atlas.com and registered the GA4 custom definitions; context at 60%
---

# Handover — editorial restyle + SEO/growth/analytics audit of esp-atlas.com

## Mission

Two work items, in this order, for a fresh session on the repo `/Users/fcavalcanti/dev/esp-atlas` (public GitHub `fcavalcantirj/esp-atlas`, production at https://esp-atlas.com):

**(A) Editorial restyle.** Port the new look & feel from `/Users/fcavalcanti/Downloads/esp-atlas.zip` onto `main` and finish where needed. The zip is a typographic/geometric reskin (Newsreader serif + Geist Mono, squared radii, flat full-bleed header, type-scale tokens) on top of the current HEAD; the color palette and component tree are unchanged. Felipe's words: "look how neater". Ships first, so the audit measures the final UI.

**(B) SEO / growth / analytics audit.** Act as a senior technical-SEO engineer, growth hacker and digital-analytics consultant; review the entire property and codebase; deliver the 13-section audit in the Appendix spec verbatim, as a repo doc `docs/seo-audit/2026-08-22.md` (PR), with code fixes as separate PRs, prioritized by an effort-vs-impact matrix.

"Done" = (A) live on esp-atlas.com with CI green and screenshots checked at desktop + mobile, light + dark; (B) audit doc merged, 0–30-day critical fixes opened as PRs, each green on CI, nothing merged without Felipe's go.

This work is the follow-up to PR #2 (desktop two-column explorer, GA4 via `@next/third-parties`, theme/text-size controls, SSR part pages, facets API, compare picker, footer).

## Where things stand (verified)

### Product and deployment
- [REAL] Production = `main` at `589ef35` (`feat(web): prod polish — … (#2)`), verified 2026-08-22 ~14:30 UTC by `gh api`/`git log origin/main` and by curl against https://esp-atlas.com: `/api/health` → `{"status":"ok","count":94}`; `/api/facets` 200; `/api/parts/xiao-esp32c6` returns `frontmatter`, `body`, `chain.soc.id == "esp32-c6"`, `related` (6); `/api/search?soc=esp32-h2&type=board` → `["esp32-h2-devkitm-1"]`; `/parts/m5stack-cores3` HTML contains `<title>CoreS3 (m5stack) — Board specs · esp-atlas` and a `<meta name="description">`; `/parts/nope` → HTTP 404; `/sitemap.xml` → 96 `<loc>`; `/robots.txt` allows `/`, disallows `/api/`, names the sitemap; home HTML contains `googletagmanager.com/gtag/js?id=G-66L7SDXKJZ` and the classes `home-layout`, `home-sidebar`, `site-footer-grid`.
- [REAL] Vercel: team `flowcoders`, project `esp-atlas`, **Root Directory `apps/web`**. The Python API is a Vercel serverless function at `/api` made of `apps/web/api/index.py` + `apps/web/vercel.json` + `apps/web/requirements.txt` + the `vercel-build` script in `apps/web/package.json` (copies `data/`, `schema/`, `esp_atlas_core`, `esp_atlas_api` into `apps/web/api/_bundle/`, gitignored). Documented in `DEPLOY.md` (rewritten in PR #2; accurate). Preview deployments are behind Vercel login (server-to-server fetches get 302 to Login) — observed on the PR #2 preview.
- [REAL] Repo layout: `apps/core` (`esp_atlas_core`: SQLite FTS5 index, `search`, `get_part`, `facets`, `wizard`, `validate`), `apps/api` (FastAPI: `/health /search /wizard /parts /parts/{id} /facets /validate`, plus `/docs`), `apps/cli` (`esp-atlas` click CLI), `apps/web` (Next.js 16.3.2 / React 19.2.8, App Router, vanilla CSS in `app/globals.css`, no Tailwind), `data/` (94 datasheet-cited markdown records: 11 SoCs, 6 modules, 77 boards), `schema/`, `scripts/`. Deep facts in `PROJECT_KNOWLEDGE.md` at the repo root (local, untracked).
- [REAL] Web pages: `/` (static shell; wizard + search + results are client-rendered from `/api`), `/parts/[id]` (server-rendered, `generateMetadata`, client fallback `PartDetailClient` when the API is unreachable from the server), `/compare?ids=a,b,c` (static shell + client), `/sitemap.xml` (`force-dynamic`, lists static routes + every part), `/robots.txt`, `/icon.svg`, `not-found.tsx`, `error.tsx`. Server-side API base resolved in `apps/web/lib/api-server.ts` (`API_INTERNAL_URL` → absolute `NEXT_PUBLIC_API_URL` → `https://$VERCEL_PROJECT_PRODUCTION_URL/api` in production → `http://localhost:8000`), 3 s timeout, 1 h fetch cache.
- [REAL] Analytics in code: `apps/web/lib/analytics.ts` (`track()` over `sendGAEvent`, ~20 event names, params truncated to 100 chars), `lib/site.ts` (`GA_ID = NEXT_PUBLIC_GA_ID || (production ? "G-66L7SDXKJZ" : undefined)`), `<GoogleAnalytics gaId>` in `app/layout.tsx`. Full event/param table in `apps/web/README.md` ("Analytics").

### CI, branch protection, accounts
- [REAL] `.github/workflows/validate.yml` runs jobs `schema` (validate.py + build_index.py), `tests` (pytest over core/api/cli on Python 3.12), `sources-live` (`continue-on-error`). Branch protection on `main` (checked via `gh api repos/fcavalcantirj/esp-atlas/branches/main/protection`, 2026-08-22): required status checks `["schema","tests"]`, `strict: true`, 0 required reviews. A direct `git push origin main` was rejected ("protected branch hook declined"). PR #2 was squash-merged with `gh pr merge 2 --squash --delete-branch`.
- [REAL] `gh` keyring on this Mac holds two accounts: `fcavalcanti-onvida` (active; **no push/admin** on this repo) and `fcavalcantirj` (repo owner). PR create/merge and repo settings need:
  ```
  gh auth switch --user fcavalcantirj
  # … gh pr create / gh pr merge …
  gh auth switch --user fcavalcanti-onvida
  ```
  `git push` over SSH authenticates as `fcavalcantirj` regardless (`ssh -T git@github.com` → "Hi fcavalcantirj!").
- [REAL] GitHub Discussions enabled 2026-08-22 (`gh api -X PATCH repos/fcavalcantirj/esp-atlas -F has_discussions=true` → `has_discussions: true`); the footer links to `/discussions` and `/issues`.
- [TEST] 180 pytest pass (`apps/core/tests apps/api/tests apps/cli/tests`); `python3 scripts/validate.py` → `94/94 valid, 0 error(s)`; `npx tsc --noEmit`, `npm run lint`, `npm run build` clean at `589ef35` (`/` and `/compare` static, `/parts/[id]` and `/sitemap.xml` dynamic).

### Google Analytics 4 / Search Console
- [REAL] GA4 property `properties/551132215` ("esp-atlas-web"), web data stream `properties/551132215/dataStreams/15482230279`, measurement ID `G-66L7SDXKJZ`. On 2026-08-22 via the Analytics Admin API (`v1alpha`, read back after writing): 20 event-scoped custom dimensions with parameter names `part_id part_type origin q needs filters form budget radio band protocol type field theme link_type preset relation part_ids removed_key host` and 6 event-scoped custom metrics `result_count position scale selected_count needs_count filter_count` (unit STANDARD). Display names for `radio`/`band`/`protocol` are "WiFi standard", "WiFi band", "Mesh protocol" (Google rejects `-` and `.` in display names). Enhanced measurement was already `streamEnabled: true, pageChangesEnabled: true, outboundClicksEnabled: true` — not changed.
- [REAL] Service account `esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com` in GCP project `esp-atlas-ga4` (created 2026-08-22; `analyticsadmin.googleapis.com` and `iam.googleapis.com` enabled). Felipe granted it **Editor** on the GA4 property through the GA UI. Its only key (`799a47a7…`) was revoked and deleted after use. To use it again, Felipe (logged into gcloud as `felipe.cavalcanti.rj@gmail.com`) mints a key:
  ```
  gcloud iam service-accounts keys create <scratchpad>/ga4-sa.json --iam-account=esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com --project esp-atlas-ga4
  ```
  For the GA4 **Data API** (reports) enable `analyticsdata.googleapis.com` on `esp-atlas-ga4` first. For Search Console, the same SA email must be added as a user in GSC (Felipe) and `searchconsole.googleapis.com` enabled.
- [UNVERIFIED] Google Search Console is verified for esp-atlas.com — stated by Felipe 2026-08-22, not checked from this session.
- [REAL] `NEXT_PUBLIC_GA_ID` is **not** set in the Vercel project (the Vercel CLI scope available here does not contain the project); production relies on the code default `G-66L7SDXKJZ`.

### The restyle zip (analysis by an Explore agent, 2026-08-22; extracted to a scratchpad, never into the repo)
- [REAL] Zip root = `apps/web/` flattened to the top level, plus byte-identical copies of `apps/api`, `apps/core`, `data/`, `schema/`. Based on HEAD `589ef35`: every file under `app/`, `components/`, `lib/` is byte-identical to the repo **except these 8**:
  - `app/globals.css` — 1512 → 1803 lines, additive. Same 14 color tokens with identical hex values in light and dark. Adds type-scale tokens `--t-display/-title/-lede/-body/-sm/-xs/-micro`, `--lead-*`, `--track-*`, `--page-x` (shared gutter for header/main/footer), `--font-language` (serif) and `--font-data` (mono); drops `--font-geist-sans`; radii `3px / 2px / 2px`; header flat opaque `var(--bg)`, no blur, `max-width: none`, `--header-h: 52px`; 15px base (`93.75%`), `clamp()` scale (`h1` up to 4.25rem), `--lead-body: 1.65`, `oldstyle-nums`, ligatures, `hanging-punctuation`. No Tailwind directives anywhere.
  - `app/layout.tsx` — `Geist` → `Newsreader` from `next/font/google` (weights + `style: ["normal","italic"]`, `display: "swap"`), CSS variable `--font-geist-sans` → `--font-serif`; `Geist_Mono` unchanged.
  - `components/SiteHeader.tsx`, `components/SiteFooter.tsx` — remove `SITE_EMOJI` and the `.site-logo-mark` span; footer adds `.footer-standfirst`.
  - `components/PartResultCard.tsx` — title wrapped in `<h3 className="part-card-title">`, meta in `<p className="part-card-meta">`, `.part-card-head` added, `.part-card-pill` dropped.
  - `components/HeaderControls.tsx` — `☀`/`☾` replaced by inline SVG sun/moon.
  - `lib/api.ts` — drops the dev fallback (`API_BASE = NEXT_PUBLIC_API_URL || "/api"`). **Do not take** — it relies on a `next.config.mjs` rewrite proxy that the repo does not use.
  - `package.json` — renamed `"my-project"`, adds `@base-ui/react @vercel/analytics class-variance-authority clsx lucide-react shadcn tailwind-merge tw-animate-css tailwindcss@4 @tailwindcss/postcss postcss`, **removes `eslint`, `eslint-config-next`, the `lint` script and the `vercel-build` script**, loosens pins. **Do not take.**
- [REAL] Zip-only vestigial scaffolding from the design tool (nothing imports it): `components.json`, `components/ui/button.tsx`, `lib/utils.ts`, `next.config.mjs`, `postcss.config.mjs`, `pnpm-lock.yaml`, `esp-atlas.db`, `public/placeholder-*.{png,svg,jpg}`. Repo-only files the zip lacks (deploy-critical): `apps/web/api/index.py`, `vercel.json`, `requirements.txt`, `eslint.config.mjs`, `next.config.ts`, `package-lock.json`, `.env.example`, `README.md`.
- [REAL] Completeness: zero `TODO/FIXME/XXX` in the zip's `app/ components/ lib/`; every `@/…` import resolves; every `className` literal in the zip's TSX has a selector in the zip's `globals.css`; the only selector present in the repo but absent from the zip is `.site-logo-mark`, which nothing in the zip references.

### Local development recipe (verbatim, worked 2026-08-22)
- [REAL] Port 8000 on this Mac is held by a Docker container (`com.docker` LISTEN) — not ours, do not kill. Use 8010:
  ```
  python3 -m venv <scratchpad>/venv && <scratchpad>/venv/bin/pip install pytest jsonschema pyyaml httpx fastapi click uvicorn
  cd /Users/fcavalcanti/dev/esp-atlas
  PYTHONPATH=$PWD/apps/core/src:$PWD/apps/api/src:$PWD/apps/cli/src <scratchpad>/venv/bin/python -m pytest apps/core/tests apps/api/tests apps/cli/tests -q
  PYTHONPATH=$PWD/apps/core/src:$PWD/apps/api/src ESP_ATLAS_DB_PATH=<scratchpad>/esp-atlas-dev.db <scratchpad>/venv/bin/uvicorn esp_atlas_api.main:app --port 8010
  cd apps/web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run dev
  ```
  Web checks: `cd apps/web && npx next typegen && npx tsc --noEmit && npm run lint && npm run build` (`next typegen` generates the `PageProps`/`LayoutProps` route types that `tsc` needs on a fresh checkout). Kill previous `uvicorn`/`next dev` processes before starting new ones (house rule).
- [REAL] Screenshots: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1300 --virtual-time-budget=8000 --screenshot=<out.png> <url>`. Headless Chrome will not lay out narrower than ~500px, so for 390px use a wrapper file `<iframe src="http://localhost:3000/…" style="width:390px;height:2300px;border:0">` and screenshot that at `--window-size=600,2300`.
- [REAL] The Context7 MCP plugin is over its monthly quota on this machine; use WebFetch on official docs instead.

## Blocking constraints (builder: restate these before planning)

1. `main` is protected: every change goes through a PR that passes the `schema` and `tests` checks (strict, branch up to date); never push to `main`; squash-merge like #1/#2; `gh` must be switched to `fcavalcantirj` for PR create/merge and switched back afterwards.
2. Never delete or replace the Vercel glue: `apps/web/api/index.py`, `apps/web/vercel.json`, `apps/web/requirements.txt`, the `vercel-build` script, `eslint.config.mjs`, `next.config.ts`. Adopting the zip's `package.json`, `next.config.mjs`, `postcss.config.mjs` or Tailwind/shadcn deps breaks production and removes lint.
3. "Smart API, dumb client" (`INTERFACE-SPEC.md`): ranking, filtering and any data derivation live in `esp_atlas_core`; the web app only calls the API and renders. SEO features that need data (hub pages per SoC/brand, related lists, counts) use the existing endpoints (`/facets`, `/search?soc=&type=`, `/parts/{id}`, `/parts`) or add core function + API route + tests first.
4. `data/` is datasheet-cited, source-or-omit (`AGENTS.md`, `CONTRIBUTING.md`); the audit must not add or edit records without an official citation; `price_tier` is editorial and must never be rendered or marked up as a spec.
5. No secrets in the repo. The GA measurement ID is public by nature. Service-account keys live only in the session scratchpad and are revoked after use. A Composio API key appeared in an earlier chat — it is not to be reused or written anywhere.
6. GA4 event names and parameter names are contracts with the registered custom definitions (table in `apps/web/README.md`); renaming a param silently breaks reporting. Add new events/params rather than renaming, and register new params in GA4 (Admin API via the SA) when you add them.

## Accepted residuals / Refuted — don't fix

- Composio's Google Analytics toolkit: read-only tools worked, but Google hard-blocks Composio's shared OAuth app for `analytics.edit` ("This app is blocked"). gcloud ADC with extra scopes is blocked the same way. The service account is the only working write path — do not retry OAuth routes. Dead Composio objects `ac_TSXc32G1v0PM` and `ca_-pzKugk-0W6L` can be ignored.
- `apps/web/app/parts/[id]/loading.tsx` was deliberately removed: with it present, unknown ids streamed an HTTP 200 shell before `notFound()` fired. Do not reintroduce a loading file on that route.
- Wizard `score` is the same constant for every result of a query (sum of asked needs) — the UI hides it on purpose and shows "why it matches" reasons; do not "fix" ranking in the web app (constraint 3).
- `/ask` (Groq chat) is designed but deliberately not built (INTERFACE-SPEC M2); out of scope.
- A cookie-consent banner for GA was considered and decided **no** (Felipe, 2026-08-22).
- Root `DEPLOY.md` was rewritten in PR #2 to the real `apps/web` layout; `ARCHITECTURE.md`/`SPEC.md` still describe `index.json`-on-GitHub-Pages and a `/ask` route that do not exist — known, harmless, not a bug to fix in this work (mention in the audit as doc drift if relevant).
- In zsh, never name a shell variable `path` — it clobbers `$PATH` (burned once this session).

## Hard rules & human-reserved decisions

- Commit messages: one-line conventional subject (`feat(web): …`, `fix(seo): …`, `docs(seo): …`), body optional, trailer `Co-Authored-By: Claude <noreply@anthropic.com>` (use your model name). Commit, push and open PRs for this work — Felipe has authorized the restyle end to end ("whole nine yards"); **merging each PR** still waits for his go.
- The zip is the design reference, including removal of the 🧭 mark from the header; `app/icon.svg` (favicon) stays. Further visual changes beyond the zip are NOT wanted unless needed to "finish" something the zip left inconsistent.
- Launch/visibility, domain aliases (`esp-atlas.dev`), monetization/affiliates (an explicit anti-goal in `SPEC.md`), paid SEO tooling (Ahrefs/Semrush/etc.), newsletters or social accounts ARE FELIPE'S CALL — never assume them.
- Which growth experiments get built IS FELIPE'S CALL — propose, rank, do not implement beyond the 0–30-day technical fixes without approval.
- Anything that changes `data/` records IS FELIPE'S CALL unless it is a datasheet-cited correction.

## Acceptance checklist (the author approves the plan ONLY against these)

1. The plan restates all six blocking constraints correctly, in the builder's own words, before anything else.
2. The restyle step copies exactly these six files from the zip into `apps/web/`: `app/globals.css`, `app/layout.tsx`, `components/SiteHeader.tsx`, `components/SiteFooter.tsx`, `components/PartResultCard.tsx`, `components/HeaderControls.tsx`; keeps the repo's `lib/api.ts`, `package.json`/`package-lock.json` (no dependency from the zip's list is added; `next/font/google` Newsreader needs no package), ESLint config, `vercel-build`, `next.config.ts`, and everything under `apps/web/api/`; adds none of the zip-only scaffolding.
3. Restyle verification is spelled out: `npx next typegen && npx tsc --noEmit && npm run lint && npm run build`; screenshots at 1440px and 390px (iframe trick) of `/`, `/parts/xiao-esp32c6`, `/compare?ids=esp32-c6,esp32-h2,xiao-esp32c6`, in light and dark (`[data-theme="dark"]`), before opening the PR; after merge, prod curl checks (SSR `<title>`, `/parts/nope` → 404, `/sitemap.xml` count, GA tag present).
4. The audit plan names the evidence source per spec section and how it is obtained: crawl of production (curl + headless Chrome, `view-source` for metadata/JSON-LD), PageSpeed Insights API for CWV/Lighthouse (mobile + desktop, home + a part page + compare), GSC Performance API and GA4 Data API through the service account (key and GSC user grant requested from Felipe), sitemap/robots/canonical checks, internal-link graph from the rendered HTML. Sections without data (backlink profile without a paid tool, competitor share of voice) are marked as limitations with the cheapest way to get the data — never guessed.
5. The audit is delivered at `docs/seo-audit/2026-08-22.md`, follows the Appendix spec section by section (all 13, in order, every bullet addressed or explicitly N/A), tags every recommendation Critical/High/Medium/Low, includes an effort-vs-impact matrix, and separates "ship now" PRs (0–30 days) from the roadmap.
6. Technical fixes are listed with file paths and respect constraint 3. At minimum the plan evaluates and decides on: JSON-LD (`WebSite` + `SearchAction` on `/`, `BreadcrumbList` on part pages, and `Product`/`TechArticle`/`Dataset` — justify the choice — for parts), per-SoC and per-brand hub pages (server-rendered, programmatic, fed by `/search?soc=` / `/facets`; route naming recommendation), `opengraph-image` (static or per-part via `next/og`), canonical and trailing-slash consistency, the `/compare?ids=` indexing policy (canonical to `/compare` and/or `noindex`), internal links from `/` to hubs and top parts (the home's results are client-only and invisible to crawlers), `lastModified` in `sitemap.ts` (from records' `verified` dates or git), serving `llms.txt` at `https://esp-atlas.com/llms.txt`, image/alt usage, H1 uniqueness, and the thin-content risk of 94 near-identical part pages.
7. The analytics part of the plan covers: GA4 key events to mark (`result_click`, `outbound_click`, and whether `wizard_submit` should be one), GSC ↔ GA4 property linking, UTM conventions for the GitHub/Discussions/contribute links, a yes/no recommendation on Vercel Analytics + Speed Insights (the zip's `package.json` includes `@vercel/analytics` — decide explicitly), and a check that the registered custom dimensions match `lib/analytics.ts` params.
8. Order of work is restyle PR → audit doc PR → fix PRs (one concern per PR), each green on CI, each merged only after Felipe's go.
9. The plan ends with `## Concerns` (each HIGH/MEDIUM/LOW) and `## Questions for the author`, and answers the three Open questions below.

## next_action

After APPROVED: `git fetch origin && git checkout -b restyle/editorial-newsreader origin/main`, `unzip -q -o /Users/fcavalcanti/Downloads/esp-atlas.zip -d <scratchpad>/design-zip`, copy the six files from checklist item 2 into `apps/web/`, run the verification chain and screenshots, commit, push, `gh auth switch --user fcavalcantirj && gh pr create …`, switch `gh` back.

## Open questions

1. Fonts: the zip keeps Geist Mono for data (`--font-data`) and uses Newsreader for language — confirm both are loaded via `next/font/google` only (no extra package), and whether `display: "swap"` causes a visible CLS on part pages (measure with PSI).
2. `/compare?ids=…`: `noindex` + canonical to `/compare`, or let a few curated comparisons be indexable landing pages (e.g. "ESP32-C6 vs ESP32-H2")? Recommend one with reasoning.
3. Hub pages: new routes (`/socs/esp32-c6`, `/brands/seeed`) versus enriching the existing `/parts/<soc-id>` page with the full "boards on this chip" list and making it the hub — recommend one; consider crawl depth, duplicate-content risk, and constraint 3.

## Pointers

- Repo: `/Users/fcavalcanti/dev/esp-atlas` (branch `main`, HEAD `589ef35`). Deep codebase facts: `PROJECT_KNOWLEDGE.md` (repo root, local/untracked). Docs: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SPEC.md`, `ARCHITECTURE.md`, `INTERFACE-SPEC.md`, `DEPLOY.md`, `COVERAGE.md`, `apps/web/README.md` (env vars + analytics taxonomy), `apps/api/README.md`, `apps/core/README.md`.
- Design reference: `/Users/fcavalcanti/Downloads/esp-atlas.zip` (extract to a scratchpad only).
- Production: https://esp-atlas.com · API docs https://esp-atlas.com/api/docs · repo https://github.com/fcavalcantirj/esp-atlas · PR #2 https://github.com/fcavalcantirj/esp-atlas/pull/2 · Discussions https://github.com/fcavalcantirj/esp-atlas/discussions
- Google: GA4 `properties/551132215` (measurement `G-66L7SDXKJZ`, stream `15482230279`); GCP project `esp-atlas-ga4`; service account `esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com` (Editor on the property; key minted by Felipe on request, revoke after use).
- Secrets: none in the repo; `.env*` files are gitignored; Vercel env vars are in the Vercel dashboard (project `flowcoders/esp-atlas`), not reachable from this machine's Vercel CLI scope.

## Appendix — Felipe's audit task spec (verbatim)

**Task**: You are to act as a senior SEO engineer, growth hacker, and digital analytics consultant with deep technical SEO expertise.
Carefully review and analyze the *entire website/digital property and its underlying codebase* (rendering strategy, routing, metadata, structured data, content architecture, internal linking, performance, analytics integrations, and acquisition funnels). Then, deliver a structured, detailed, and comprehensive SEO, growth, and analytics audit.

**Instructions for your output**:
Present your findings in the following sections, in order:

1. **Executive Summary**
   * Purpose of the product and the search intent it should capture
   * Current SEO health score and visibility metrics
   * Target audiences, primary keyword clusters, and competitive positioning overview
   * Key opportunities and critical issues identified
   * Expected impact and prioritized recommendations

2. **Technical SEO & Rendering Architecture**
   * Rendering/delivery strategy (SSR / SSG / CSR / hybrid) and justification from a crawlability standpoint
   * Rendering issues blocking indexation (client-side-only content, broken hydration, blocked resources)
   * Site architecture, URL structure, routing, and crawlability assessment (text or ASCII diagram of page hierarchy and link flow)
   * Page speed and Core Web Vitals performance (LCP, INP, CLS) and ranking impact
   * Mobile responsiveness and usability
   * Indexation status, XML sitemap, crawl budget, and indexation controls
   * Robots.txt and meta robots implementation
   * Schema markup and structured data evaluation (JSON-LD / schema.org types present or missing)
   * HTTPS, security, canonicalization, and redirect handling

3. **On-Page SEO Evaluation**
   * Title tags, meta descriptions, Open Graph, and Twitter card implementation
   * Header structure (H1–H6) and keyword targeting
   * Content quality, relevance, and E-E-A-T signals
   * Internal linking structure, anchor text distribution, orphan pages, and broken links
   * Image optimization and alt text implementation
   * URL structure and breadcrumb navigation

4. **Content Strategy & Programmatic Growth**
   * Content gap analysis and keyword opportunities
   * Search intent alignment, topic clusters, and landing-page mapping
   * Content lifecycle: how content is created, published, updated, and retired (and whether it is programmatic/scalable)
   * Programmatic SEO readiness: templated pages, dynamic routes, data-driven content at scale
   * Content freshness and update frequency
   * Duplicate content, thin pages, and cannibalization issues
   * Featured snippet and SERP feature optimization potential
   * Challenges when expanding to new keyword clusters, locales, or content types

5. **Off-Page SEO, Authority & Growth Loops**
   * Backlink profile analysis and domain authority
   * Link quality, diversity, and anchor text distribution
   * Brand mentions and citation consistency
   * Competitor backlink gap analysis
   * Toxic links and disavow file requirements
   * Non-search growth loops: referral, social sharing, viral mechanics, embeds, UGC
   * Dependency on a single channel or platform-policy changes

6. **Analytics & Tracking Infrastructure**
   * Google Analytics 4 implementation and configuration
   * Conversion tracking and goal setup
   * Event tracking and engagement metrics
   * Cross-domain tracking, UTM hygiene, and data accuracy
   * Google Tag Manager container organization
   * Search Console integration and performance data
   * Tracking and attribution gaps

7. **User Experience & Engagement Metrics**
   * User flow and behavior analysis
   * Bounce rate and session duration patterns
   * Page-level engagement and scroll depth
   * Site search usage and query analysis
   * Device and browser performance variations

8. **Local SEO & International Considerations**
   * Google Business Profile optimization (if applicable)
   * NAP consistency and local citations
   * Hreflang implementation for international sites
   * Geographic targeting and content localization
   * Local schema markup and reviews integration

9. **Competitive Analysis**
   * Share of voice and visibility comparison
   * Keyword ranking gaps and opportunities
   * Content strategy differentiation
   * Technical implementation benchmarking
   * Backlink profile comparison

10. **Risks & Penalty Exposure**
    * Spammy patterns, doorway pages, cloaking, AI-generated thin content
    * Algorithm update vulnerability
    * Security or performance regressions that threaten rankings

11. **Performance Tracking & KPIs**
    * Current baseline metrics and historical trends
    * Recommended KPI framework and dashboards
    * Attribution modeling and conversion paths
    * ROI measurement and forecasting methodology
    * Reporting cadence and stakeholder communication

12. **Growth Experiments**
    * Proposed experiments with hypotheses, success metrics, and required instrumentation
    * Ranked by expected impact and effort

13. **Action Plan & Roadmap**
    * Critical fixes (0–30 days)
    * Quick wins (30–60 days)
    * Strategic initiatives (60–180 days)
    * Long-term optimization projects (6+ months)
    * Resource requirements and team responsibilities
    * Success metrics and milestone tracking

**Output requirements**:
* Use clear headings with priority indicators (Critical/High/Medium/Low)
* Include specific metrics, scores, and benchmarks where available
* Provide actionable recommendations with expected impact
* Include screenshots or data visualizations where helpful
* Reference industry best practices and Google guidelines
* Be explicit about trade-offs, assumptions, and data limitations
* Keep explanations focused on SEO, discoverability, analytics, and growth only
* Prioritize recommendations by effort vs. impact matrix
