# SPEC — Firmware index: user-selectable ordering

Status: DRAFT (for review). Author: session 2026-09-22.
Trigger: `/firmware` renders one fixed order (popularity desc) with **no user control**.
Felipe: "spec an ordenation like alphabetic, stars, etc. — there's no ordenation." Goal:
give the user a sort control, **server-side** (Golden Rule 3: ordering is domain logic —
the API sorts, the client only picks and renders), reusing the comparator authority that
already exists in `esp_atlas_core`.

## 0. Grounding (verified in source, not assumed)

- **The endpoint already sorts server-side.** `apps/api/src/esp_atlas_api/main.py:410`
  `GET /firmware` takes `sort: Literal["popularity","name"] = "popularity"`, `limit`,
  `offset`, and returns `total`. `popularity` routes through `core_sort_by_popularity`
  (`esp_atlas_core.firmware.sort_by_popularity` / `popularity_key`) — the **single shared
  comparator** whose docstring exists so `/firmware` and `/examples` "can never diverge".
- **But two gaps:** (a) the web page never sends `sort` — `fetchFirmwareList()`
  (`apps/web/lib/api-server.ts:101`) hardcodes `/firmware`, and `app/firmware/page.tsx`
  reads no `searchParams`; so the control doesn't exist in the UI. (b) the `name` branch
  is a **naive inline `sorted(records, key=lambda r: r["name"])`** — case-sensitive, no
  tie-break, no null rule — it bypasses core, the one place ordering is supposed to live.
- Sortable fields on each record (`esp_atlas_core.firmware.list_firmware` frontmatter):
  `name`, `popularity.stars`, `popularity.forks`, `category`, `socs[]`, `capabilities[]`.
- **Board/recipe count** ("runs on N boards") is not on the record, but is computable
  server-side now with zero new collection: `recipes_for_firmware(id)` /
  `list_recipes()` (`esp_atlas_core.firmware`). Projection only (§4.A) → v1.
- **Repo last-push** ("recently updated") is persisted nowhere, BUT already fetched and
  discarded: `jr/tools.py:279` reads `pushed_at` from `gh api repos/OWNER/REPO`, comments
  it "staleness signal for refresh", drops it. Plumbing + backfill (§4.B) → v1.1.
  ⚠️ `popularity.as_of` is when **we polled GitHub**, NOT when the repo changed — never
  sort on it and call it "updated"; only `pushed_at` is truthful.
- Coverage (popularity spec): 117/117 have `popularity.stars`; range 94,567 → single
  digits. No nulls today, but the comparator must still define null placement.
- `/firmware` page is ISR (`revalidate=300`), `canonical: /firmware`.

## 1. Scope decision (made, override if wrong)

**Server-side sort via the existing `?sort=` param — extend it, don't rebuild.** All
comparators live in `esp_atlas_core` as the single source of truth (like `popularity_key`
today), each pinned by a deterministic oracle (§5). The client sort control just changes
the `sort` query param and re-renders; it computes no ordering.

Rejected: client-side re-sort of the already-loaded list. It's the faster shortcut but
**violates Golden Rule 3** (frontend calculating domain order) and would spawn a SECOND
ordering authority in JS — exactly what `popularity_key`'s "can never diverge" docstring
warns against. Curl-litmus (Rule 3): `GET /firmware?sort=name` must return correctly
ordered JSON on its own.

Home `ExamplesGrid` stays out of scope (its `FirmwareExample` projection carries none of
these keys — popularity spec §0).

## 2. Sort options

Default stays **popularity** (stars desc) — do not change the landing order; SEO and the
"ranked by GitHub popularity" lead copy depend on it.

**v1** (extend the `sort` Literal to these; each maps to a core comparator):

| UI label               | `?sort=`     | Core comparator (single source of truth)              |
|------------------------|--------------|-------------------------------------------------------|
| Most stars *(default)* | `popularity` | `popularity_key` — stars desc, forks desc, name asc   |
| Name (A→Z)             | `name`       | `name_key` — casefold asc, then id (stable)           |
| Name (Z→A)             | `name-desc`  | reverse of `name_key`                                 |
| Most forks             | `forks`      | `forks_key` — forks desc, stars desc, name asc; null last |
| Runs on most boards    | `boards`     | `boards_key` — recipe count desc, then `popularity_key` |

**v1.1** (after §4.B):

| UI label         | `?sort=`  | Core comparator                                          |
|------------------|-----------|----------------------------------------------------------|
| Recently updated | `updated` | `updated_key` — `pushed_at` desc; missing/null sorts last |

Category is a *filter*, not a sort — separate spec.

## 3. Behavior / edge rules

- **Comparators live in core**, one module, mirroring `popularity_key`'s shape
  `(bucket, *keys, tiebreak)` with **nulls in a trailing bucket** so `undefined`/`None`
  never poisons ordering. `name` is compared **casefolded**; final tie-break is always
  `id` → fully deterministic (oracle depends on it).
- **Fix the existing `name` branch**: replace the inline lambda with `name_key`. Its
  current case-sensitive, tie-break-less behavior is a latent bug the oracle will catch.
- **API contract**: extend the `sort` Literal; unknown value → 422 (FastAPI default) or
  clamp to `popularity` — pick clamp for resilience, state it in the docstring. `limit`
  applies **after** sort (already true). `total` unchanged.
- **Web wiring**: `page.tsx` reads `searchParams.sort`, passes to
  `fetchFirmwareList(sort)`; the control is a set of **real links / a `<form method=GET>`**
  so it works with **no JS** (Rule 3 — no client compute) and each order is a shareable
  URL. `FirmwareBrowseList` renders whatever order the server returned; `useReveal`
  overflow cap unchanged.
- **SEO**: bare `/firmware` (no param) stays the ISR-static, indexable canonical. `?sort=`
  variants render dynamically, emit `robots: noindex, follow`, and keep
  `canonical → /firmware` so the 5 orders don't become 5 indexable near-duplicates.
- **Empty/cold API**: unchanged — empty list, existing `noindex` path (page.tsx).

## 4. Data plumbing

### 4.A Board count → `boards: int` (v1, cheap, same PR)

Edges already on disk; no new collection.

1. **core** — `list_firmware()` projects `boards` per record. Count in ONE pass: build a
   `Counter` keyed by recipe `firmware` id from `list_recipes()`, not an O(n²)
   `recipes_for_firmware` per record.
2. **api** — add `boards: int = 0` to `FirmwareRecord`
   (`apps/api/src/esp_atlas_api/models.py:399`).
3. **web** — add `boards: number` to `Firmware` (`apps/web/lib/api.ts`); optionally render
   "Runs on N boards" on `FirmwareCard`.
4. **bundle/guard** — regenerate `apps/web/api/_bundle/` (never hand-edit); this touches
   `apps/core`+`apps/api`, so run the **full `apps/core` suite**, not just the API subset
   (schema/count edits pass the subset but break full CI and stall Jr ticks — house rule).

### 4.B Repo last-push → `popularity.pushed_at` (v1.1, plumbing + backfill)

Value is already fetched then discarded — persist, then backfill.

1. **capture** — `jr/tools.py:279` already has `d.get("pushed_at")`; thread it into the
   popularity snapshot built at `jr/tools.py:545` (`{"stars","forks","as_of"}` → add
   `"pushed_at"`).
2. **persist** — `jr/writers.py` `if popularity:` block (~L316): copy `pushed_at` into
   `pop_fm` when present.
3. **model** — `pushed_at: Optional[str] = None` on `Popularity`
   (`apps/api/src/esp_atlas_api/models.py:404`) + `pushed_at?: string | null` on
   `FirmwarePopularity` (`apps/web/lib/api.ts`).
4. **backfill** — 117 records lack `pushed_at`; one-time Jr/`scripts/` re-poll writes it
   into each `firmware.md`, re-stamps `as_of`. Until then `updated_key` treats missing as
   null → last.
5. **floor audit** — confirm `scripts/firmware_floor_audit.py` + popularity schema still
   pass with the additive key (should; verify).

## 5. Oracle & tests (backend-TDD FIRST, then UI — house rule)

1. **Comparator oracle (pure, deterministic)** — golden fixture in
   `apps/core/tests/` over a hand-built record set that exercises: stars ties broken by
   forks then name; forks-null; equal names broken by id; casefold (`ZephyrRTOS` vs
   `advanceos`); `boards` count desc with popularity fallback; and a null-stars row landing
   last under EVERY mode. Assert exact id order per mode. This is the oracle everything
   pins to. (v1.1 adds a `pushed_at` desc + null-last case.)
2. **API test** — `GET /firmware?sort=<mode>` returns the oracle order; `limit`/`offset`
   slice after sort; unknown `sort` clamps to popularity; `boards` present on records.
3. **Web** — `page.tsx` forwards `searchParams.sort`; control renders 4 (v1) links; default
   view byte-identical to today; non-default emits `noindex,follow` + canonical `/firmware`.

## 6. Build order (divide & conquer — one delegate run each)

- **P1 — Oracle + core comparators** (`name_key`/`forks_key`/`boards_key` + `boards`
  projection) in `esp_atlas_core`, RED→GREEN. No API wiring, no UI. Fixes the `name`
  comparator. ← implement first.
- **P2 — API surface**: extend `sort` Literal to `name-desc`/`forks`/`boards`, route each
  to its core comparator, `boards` on `FirmwareRecord`, regenerate bundle. Full `apps/core`
  + api tests green.
- **P3 — UI**: sort control on `/firmware`, `searchParams` → `fetchFirmwareList(sort)`,
  no-JS links, SEO rules (§3).
- **P4 (v1.1)** — §4.B `pushed_at` plumb + backfill + `updated` mode + oracle case.

## 7. Deferred / future

- `?sort=` is already shareable; if any sorted view should be indexable later, revisit the
  `noindex` call per-mode (default stays canonical either way).
- Same control on home `ExamplesGrid` once its projection carries `boards`/`pushed_at`.
- Category / capability / SoC **filters** (orthogonal to sort).

## 8. Acceptance

**v1:**
- `curl /firmware?sort=name|name-desc|forks|boards` each returns the oracle order,
  complete and correct on its own (Rule 3 litmus). Unknown `sort` → popularity.
- Every mode places a null-key row last; no crash on `None`/`undefined`.
- `boards` present and correct on every record (`= len(recipes_for_firmware(id))`).
- `/firmware` UI shows a sort control; default view byte-identical to today; works with JS
  disabled; non-default sorts `noindex,follow`, canonical `/firmware`.
- Full `apps/core` suite green (not just the API subset); `_bundle/` regenerated.

**v1.1:**
- After backfill, `?sort=updated` orders by real `pushed_at` desc; null/pre-backfill last;
  `as_of` never used as the key.
