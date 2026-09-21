# SPEC — Firmware popularity: show stars/forks, rank by them, load-more

Status: DRAFT (for review). Author: session 2026-09-21.
Trigger: the home firmware grid shows no popularity; browsing is alphabetical and
renders all 117 at once. Goal: surface stars/forks "at a glance", rank by them,
and stop loading the whole list up front.

## 0. Grounding (verified in source, not assumed)

- The screenshotted view is `HomeView` → `components/ExamplesGrid.tsx` (the "Run X /
  category / Runs on N boards" cards), fed by the `/examples` endpoint
  (`main.py::examples` → `core_read_examples`). Its projection is `FirmwareExample`
  (`lib/api.ts`) — **it carries no stars/forks/popularity**.
- The `/firmware` index (`app/firmware/page.tsx` → `components/FirmwareCard.tsx`) is a
  SECOND surface. It fetches `fetchFirmwareList` → `/firmware`
  (`main.py::list_firmware` → `core_list_firmware`), whose records **already include
  `popularity {stars, forks, as_of}`** (`models.py::Popularity`, `FirmwareRecord`).
  But `FirmwareCard` doesn't render popularity, and the page groups by category then
  alphabetical — never by popularity.
- Data coverage: **117/117 firmware have `popularity.stars`**; range **94,567 → single
  digits**. Forks present too. So ranking is meaningful and there are no null-stars
  cases today (but the spec must still define null behavior for future records).
- Both surfaces are server-rendered/ISR (home ISR, `/firmware` `revalidate=300`).

## 1. Scope decision (made, override if wrong)

Two surfaces show firmware lists; the request ("here", the home grid) is about browse.
**Decision:** implement the feature as ONE shared, ranked, paginated, popularity-showing
card list, and use it on BOTH surfaces:

1. **`/firmware` index = the primary ranked browse.** Default sort = popularity desc.
   This is the natural "all firmware" surface and its data already has popularity.
2. **Home `ExamplesGrid` = the same card + glance**, so the view Felipe screenshotted
   gains stars/forks and a load-more. Requires plumbing popularity into the examples
   projection (§3).

Rationale: don't build two divergent card styles. If you'd rather keep home as a small
curated teaser and put the full ranked/paginated experience only on `/firmware`, that's
the one knob to flip — say so and §3.B drops out.

## 2. UX spec

- **Glance display on the card:** a compact popularity line, e.g. `★ 94.6k · ⑂ 12.4k`.
  - Format: `94567 → 94.6k`, `1234 → 1.2k`, `<1000 → exact`. Forks same.
  - Accessible: `aria-label="94,567 GitHub stars, 12,411 forks"`; the ★/⑂ glyphs are
    `aria-hidden`. Not a link (the card already links to the firmware).
  - Show `as_of` only in a `title=` tooltip ("stars as of 2026-09-14"), not inline.
  - If `stars`/`forks` is null/absent: omit that metric silently (no "0", no empty star).
- **Ordering:** popularity desc. Tie-break: `stars desc → forks desc → name asc`
  (fully deterministic — required for the oracle in §6). Records with null stars sort
  LAST, then by name.
- **Load-more ("don't load all"):**
  - Render the ranked list, but initially reveal only the first **PAGE_SIZE = 24**
    cards. A `Show more` button reveals the next 24, etc. A final `Showing N of M`.
  - Approach (see §5 for the SSR/SEO nuance): **v1 = render-all-in-HTML, reveal
    progressively client-side.** The full ranked list is in the server HTML (crawlable,
    zero extra requests); the button just lifts a CSS/count cap. This satisfies "don't
    stare at a wall of 117" without a client round-trip and keeps SEO intact.
  - `Show more` must be a real button (keyboard focusable, `aria-expanded`-less; it
    appends, doesn't toggle). No layout shift beyond the appended rows.
  - Escape hatch for scale: if the catalog outgrows ~a few hundred, switch to server
    pagination (§4 defines the API so this is a drop-in, not a rewrite).

## 3. Backend changes

### 3.A `/firmware` list — already has popularity; add server-side sort (optional but preferred)
- `core_list_firmware()` returns full records incl. `popularity`. The web index can sort
  client/server-side. **Preferred:** add an optional `sort` query param to `/firmware`:
  `sort=popularity` (default could stay `name` for back-comfrom compat, or flip to
  `popularity`). Keep it a pure, deterministic sort in `esp_atlas_core.firmware` so it's
  unit-testable without the web layer. Tie-break exactly as §2.
- Do NOT change the record shape (popularity already there). No new fields.

### 3.B `/examples` — plumb popularity into the projection (only if §1 keeps home in scope)
- `FirmwareExample` (`models.py` + `lib/api.ts`) gains `stars?: int | null` and
  `forks?: int | null` (and optionally `as_of`). Populate from the firmware's
  `popularity` where `core_read_examples` builds each example.
- Order the examples results by popularity desc (same comparator) so the home grid is
  ranked without client re-sort.
- `response_model_exclude_none=True` already set on `/examples` → null stars omit cleanly.

### 3.C Shared comparator
- One popularity comparator in `esp_atlas_core` (e.g. `popularity_key(record)`), reused
  by both list sort and examples sort, so ordering can NEVER diverge between surfaces.
  This is the single source of truth the oracle tests pin.

## 4. API contract (for the scale escape hatch)
Define now even if v1 renders-all, so pagination is a drop-in later:
- `GET /firmware?sort=popularity&limit=24&offset=0` → `{ results: [...], total: 117 }`.
- `limit` capped (e.g. ≤100), `offset ≥ 0`, invalid → 422. Default `limit` unset = all
  (current behavior preserved). Deterministic order is what makes offset paging correct.

## 5. SSR / SEO nuance (must not regress today's wins)
- The `/firmware` index is indexable and currently renders every firmware in HTML — a
  real crawl path to all 117 (confirmed in the earlier SEO audit). **v1 must keep all
  cards in server HTML**; the load-more only hides overflow visually. If we ever move to
  client-fetched pagination, we MUST keep a crawlable path (e.g. `?page=2` server-rendered,
  or keep the sitemap as the crawl path — it already lists all firmware).
- Home grid is behind the wizard's default state; not a primary index page, lower stakes.
- No change to sitemap, canonicals, or JSON-LD required. (Optional nicety: the firmware
  index `ItemList` JSON-LD could carry `position` in popularity order.)

## 6. Oracle & tests (backend-TDD FIRST, then UI — per house rule)
1. **Comparator oracle (pure, deterministic):** golden test over a fixture set with
   known stars/forks incl. ties and a null-stars record → asserts exact ordering
   (`stars desc, forks desc, name asc, nulls last`). This is the oracle everything else
   trusts; write it RED first.
2. **`/firmware?sort=popularity` endpoint test:** returns records in comparator order;
   `limit`/`offset` slice correctly; `total` correct; invalid params → 422.
3. **`/examples` test (if §1 home in scope):** each example carries stars/forks from its
   firmware; results are popularity-ordered.
4. **UI tests:** `FirmwareCard`/`ExamplesGrid` render the formatted glance
   (94.6k, aria-label), omit the metric when null; `Show more` reveals the next
   PAGE_SIZE and updates `Showing N of M`; first paint shows PAGE_SIZE.
5. Number formatting helper (`94567→94.6k`) unit-tested incl. boundaries (999, 1000,
   999500, 1000000).

## 7. Build sequence (phased, one reviewable step each)
- **P1 — Oracle + comparator** in `esp_atlas_core` (RED→GREEN). No UI.
- **P2 — `/firmware` sort param** + tests. No UI.
- **P3 — `FirmwareCard` glance + `/firmware` ranked render + load-more** (the primary
  surface). Ship + verify live.
- **P4 — Examples projection popularity + `ExamplesGrid` glance + load-more** (the home
  view Felipe screenshotted). Ship + verify live.
- Each phase = one delegate run, guard-GREEN, land on main, verify live. Divide & conquer.

## 8. Decisions already made (override any)
- Sort default on `/firmware` flips to popularity (D1).
- PAGE_SIZE = 24 (D2).
- v1 = render-all-in-HTML + progressive reveal (not client pagination) (D3).
- Home grid IS in scope and gets popularity plumbed through examples (D4).
- k-formatting (94.6k), forks shown next to stars (D5).

## 9. Non-goals
- No new popularity data source / refresh mechanism (that's Jr's job; 117/117 covered).
- No sorting UI/dropdown in v1 (single popularity-ranked default). A `sort=` toggle can
  come later since the API supports it.
- No infinite-scroll (explicit button, per request).
