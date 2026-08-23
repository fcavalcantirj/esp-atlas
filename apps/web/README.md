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
| `NEXT_PUBLIC_GA_ID` | GA4 measurement ID. Production builds default to `G-66L7SDXKJZ` when unset; dev sends nothing unless set. |
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
values the user actually chose. Events:

| Event | Params |
|---|---|
| `wizard_submit` / `wizard_results` / `wizard_empty` | `form, budget, radio, band, type, ieee802154, usb_native, needs, needs_count, result_count` |
| `search_submit` / `search_results` / `search_empty` | `q, type, radio, band, form, protocol, filters, filter_count, has_query, result_count` |
| `preset_click`, `relax_filter` | `preset` · `removed_key, needs` |
| `result_click` | `part_id, part_type, origin (wizard\|search\|related\|compare\|browse), position` |
| `part_view`, `chain_click` | `part_id, part_type, brand, soc_ref` · `from_id, to_id, relation` |
| `compare_add` / `compare_remove` / `compare_view` / `compare_filter` | `part_id, selected_count` · `part_ids, count` · `q, type` |
| `help_tip_open`, `advanced_filters_toggle` | `field` · `panel, open` |
| `theme_change`, `font_size_change` | `theme` · `scale, direction` |
| `outbound_click` | `link_type (source\|github_edit\|github_view\|github_repo\|contributing\|agents\|issues\|new_issue\|discussions\|license\|data_folder\|llms_txt\|api_docs), url, host, part_id?, field?` |
| `api_error`, `not_found` | `endpoint, status` · `path` |

Page views come from GA4 enhanced measurement (enable "page changes based on
browser history events"). Custom parameters are only reportable after you
register them in GA4 Admin → Custom definitions: dimensions `part_id, part_type,
origin, q, needs, filters, form, budget, radio, band, protocol, type, field,
theme, link_type, preset, relation, part_ids, removed_key, host`; metrics
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
