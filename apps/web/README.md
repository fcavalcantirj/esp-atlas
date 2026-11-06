# esp-atlas-web

Next.js (App Router + TypeScript) frontend over `esp-atlas-api`. Per
`INTERFACE-SPEC.md`'s "smart API, dumb client" rule: this app never
re-implements search ranking or wizard scoring — it only calls the backend,
renders the response, forwards user input, and shows loading/error states.

## Install

```bash
npm install
```

## Configure

Copy `.env.example` to `.env.local` and point it at your running API (default
already matches):

```bash
cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_API_URL` | Browser-side API base. Unset in production (same-origin `/api`). |
| `NEXT_PUBLIC_REPO_URL` | GitHub repo for "Edit on GitHub" / contribute links (override in a fork). |
| `NEXT_PUBLIC_SITE_URL` | Canonical URL for metadata, sitemap and robots. Default `https://esp-atlas.com`. |
| `NEXT_PUBLIC_GA_ID` | GA4 measurement ID. Production deployment defaults to `G-66L7SDXKJZ`; previews need a separate ID. |
| `NEXT_PUBLIC_GA_ENABLED` | `0` disables collection; `1` enables a preview only with an explicit test ID. Production deployment is enabled by default. |
| `NEXT_PUBLIC_GA_DEBUG` | `1` tags every event with `debug_mode` for GA4 DebugView. |
| `API_INTERNAL_URL` | Server-side API base (server components, sitemap) when the Vercel defaults don't apply. |

## Run

With `esp-atlas-api` already running on port 8000 (see `apps/api/README.md`):

```bash
npm run dev
```

Open http://localhost:3000.

## Pages

- `/` — two-column explorer on desktop (sticky Wizard + Search panel, results
  grid), stacked on mobile. Dropdown options come from `GET /facets`, so a new
  form factor or price tier appears as soon as it is indexed.
- `/parts/[id]` — server-rendered part page with its own `<title>`/description
  (`generateMetadata`), inheritance chain (board → module → SoC), grouped specs
  from the record's frontmatter, prose, notes, sources with verified dates, and
  related parts on the same SoC. If the API is unreachable from the server it
  falls back to client-side fetching.
- `/compare?ids=a,b,c` — filterable picker grouped by type/brand, up to 6 parts,
  differing rows highlighted; the selection lives in the URL so it is shareable.
- `/sitemap.xml`, `/robots.txt`, `/icon.svg` — generated.

Header: theme toggle (light/dark/system via `next-themes`) and A−/A+ text size
(persisted in `localStorage`, applied before first paint). Footer: why the
project exists, contribute links (CONTRIBUTING, Discussions, Issues, AGENTS.md),
data/code licenses.

## Analytics

Google Analytics 4 via `@next/third-parties/google` (`<GoogleAnalytics>` in
`app/layout.tsx`). All interactions go through `lib/analytics.ts#track()` with the
bounded, non-text parameters. Keys containing search text, prompts, or full URLs
are omitted; their lengths may be sent instead. Set localStorage
`esp-atlas:analytics-disabled` to `1` before loading to opt out. Events:

| Event | Params |
|---|---|
| `wizard_submit` / `wizard_results` / `wizard_empty` / `wizard_error` | `form, budget, radio, band, type, ieee802154, usb_native, needs_count, result_count, status` |
| `search_submit` / `search_results` / `search_empty` / `search_error` | `q_length, type, radio, band, form, protocol, filters, filter_count, has_query, result_count, status` |
| `intent_submit` / `intent_result` / `intent_error` | `surface, q_length, kind, stage, fallback, latency_ms` |
| `guide_result` / `guide_error` | `surface, kind, outcome, status` |
| `preset_click`, `relax_filter` | `preset` (compare page) · `removed_key` |
| `example_click` | `example, kind (firmware\|needs)` — a generated home example chip |
| `result_click` | `part_id, part_type, origin (wizard\|search\|related\|compare\|browse\|brand), position` |
| `part_view`, `chain_click` | `part_id, part_type, brand, soc_ref` · `from_id, to_id, relation` |
| `compare_add` / `compare_remove` / `compare_view` / `compare_filter` | `part_id, selected_count` · `part_ids, count` · `q_length, type` |
| `help_tip_open`, `advanced_filters_toggle` | `field` · `panel, open` |
| `theme_change`, `font_size_change` | `theme` · `scale, direction` |
| `outbound_click` | `link_type (source\|github_edit\|github_view\|github_repo\|contributing\|agents\|issues\|new_issue\|discussions\|license\|data_folder\|llms_txt\|api_docs), host, part_id?, field?` |
| `api_error`, `not_found` | `endpoint, status` · `path` |
| `atlas_lens_select`, `atlas_inspect`, `atlas_recipe_inspect`, `atlas_handoff`, `atlas_search` | `lens` · `record_id, record_type, lens` · `recipe_id, tier, lens` · `record_id, record_type` · `q_length` |

The tag sends an initial `page_view`. SPA page views depend on GA4 Enhanced
Measurement's "page changes based on browser history events" setting; verify
that setting in the web stream before interpreting page view totals. GA can
also collect `page_location` with a `?q=` search term. Configure web-stream
query-parameter redaction for `q` and verify its effect in DebugView before
using query-bearing pages for analytics. See Google's [page view](https://developers.google.com/analytics/devguides/collection/ga4/views?technology=websites)
and [redaction](https://support.google.com/analytics/answer/13544947) documentation.
Custom parameters are only reportable after you
register them in GA4 Admin → Custom definitions: dimensions `part_id, part_type,
origin, q_length, form, budget, radio, band, protocol, type, field,
theme, link_type, preset, example, kind, relation, part_ids, removed_key, host`; metrics
`result_count, position, scale, selected_count, needs_count, filter_count`.

## Layout

- `lib/api.ts` — typed browser client for `/health /search /wizard /parts /parts/{id} /facets`, no logic
- `lib/api-server.ts` — server-side fetch (absolute URL resolution, 3 s timeout, 1 h cache) for SSR + sitemap
- `lib/analytics.ts`, `lib/site.ts`, `lib/github.ts`, `lib/format.ts`, `lib/frontmatter.ts` — analytics wrapper, constants, GitHub URLs, display formatting, safe frontmatter readers
- `components/HomeView.tsx` — owns explorer state; `WizardForm`, `SearchBox` are controlled forms; `ResultsPanel` renders results/empty/presets; `PartResultCard` is the shared card
- `components/part/*` — part page pieces (`PartDetailView` is shared by the server page and the client fallback)
- `components/compare/*` — picker, table, URL-synced view
- `components/HelpTip*.tsx` — one open tip at a time; outside click / Escape / another tip closes it
- `components/SiteHeader.tsx`, `HeaderControls.tsx`, `SiteFooter.tsx`, `TrackedLink.tsx`

## Test

```bash
npx tsc --noEmit
npm run lint
npm run build
```

No frontend unit tests — all ranking/filtering logic lives in `esp_atlas_core` /
`esp-atlas-api` and is covered there. Smoke-test in a browser at ~390px and
≥1024px against a live API (wizard, search, part page, compare, theme, text size).
