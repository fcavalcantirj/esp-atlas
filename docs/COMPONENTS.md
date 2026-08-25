# Component bible — apps/web

A living reference for the site's UI components: what each one is for, what
data it consumes, and the behaviour rules it must keep obeying as we iterate.
This is DOCS, not a spec — if a component's actual code and this file ever
disagree, the code wins and this file is stale; fix the file.

Read this before touching any component in `apps/web/components/`, and update
it in the same PR that changes a component's props, data shape, or rendering
rules.

## Cross-cutting principles

These hold across every component below, not just the ones that name them
explicitly.

1. **Grounded/cited only — "nothing guessed, nothing invented."** Every
   sentence a maker reads traces back to a real field on a real API response
   (`run_guide()`, `parse_intent()`, `/search`, `/examples`, recipe records).
   The one exception is `RunGuideBoard.note`, and even that is an LLM
   sentence that already survived `run_guide`'s grounding validator server
   side (see `apps/core/src/esp_atlas_core/run_guide.py` module docstring) —
   the frontend never re-validates it, never edits it, and never generates
   prose of its own. Components render facts; they do not synthesize them.

2. **The intent answer must read as reasoning, not keyword search.** The
   "Understood" line, the NEEDS/DOES NOT NEED sections, and per-board fit
   reasons exist specifically so a firmware answer reads as *why*, not just
   *what matched*. When the parse is unreadable, `HomeView` says so plainly
   ("I couldn't read that as a build goal, so these are keyword matches
   instead") rather than silently passing a keyword dump off as
   understanding.

3. **Honest states shown plainly.** "No on-board microSD", "record shows no
   on-board display", "not verifiable from structured data" — these render
   exactly as the API states them. No component hides a null/negative field
   or upgrades an unverified claim into a confident one. `TrustTierBadge` and
   the fit badge both follow the same rule: colour plus the word itself,
   never colour alone, and an unknown/omitted value still renders its raw
   string rather than nothing (`?? status`, `?? board.fit`).

4. **Never an auto-redirect.** Every "see more" affordance (the firmware
   page link under a run-guide answer, a firmware/part card title, a
   "shelf → see all" link) is a real `<Link>`/`<a>` requiring an explicit
   click. No component uses `useEffect` + `router.push` to navigate a maker
   away from an answer they didn't ask to leave.

5. **Accent/hierarchy conventions (globals.css).** `--accent` (teal) marks a
   sourced/grounded unit — e.g. `.run-guide`'s left border and its section
   overlines. `--ok` (green), `--warn` (amber), `--danger` (red), `--muted`
   (grey) are the shared "honesty" palette reused identically by
   `.tier-badge--*` and `.fit-badge--*`: known-good/ideal = ok green,
   reported/works = accent/warn, unverified/partial = warn/muted,
   broken = danger with strikethrough, unconfirmed = muted. `.chip--accent`
   is a neutral/ink chip (border + fg colour), not literally teal, despite
   the name — used for both "Understood" chips and active filter chips.

## Run-guide answer anatomy

This is the shape `RunGuideAnswer` + the surrounding `HomeView` markup renders
for a firmware-intent query (`GET /run_guide/{firmware}` under the hood). Each
piece is documented in more depth under its owning component below; this
section is the map of how they compose, top to bottom:

1. **"Understood → run `<firmware>`"** — the `intent-parse` block in
   `HomeView.tsx`. Shows what the parser understood from the maker's free
   text as accent chips, plus an honest caveat if the parse was unreadable or
   partial.
2. **Summary** — `guide.summary`, always rendered, `<=2` sentences (server
   contract), template-only unless the LLM's summary survived grounding.
3. **NEEDS section** — one line per `guide.requires[]` entry: capability
   label + `why` (the firmware author's own rationale), only rendered if
   `requires.length > 0`.
4. **DOES NOT NEED section** — one line per `guide.not_required[]` entry,
   same label+why shape, styled with the `--ok` green left border (a
   negative fact still gets positive visual weight). This is where PSRAM's
   rationale is taught explicitly when a firmware's `not_required` names it
   ("does not need PSRAM: …") — there is no dedicated PSRAM widget; it's the
   same capability-label + why rendering as everything else in this section.
5. **BENEFITS FROM chips** — deduped soft-benefit reasons pulled out of
   `guide.boards[].reasons`, only rendered if any exist.
6. **BOARDS list** — one card per `guide.boards[]` entry, **in the array's
   own order — boards are ordered best-fit-first by the API** (`ideal` before
   `works`/`works-with-tradeoff` before `unconfirmed`; see
   `esp_atlas_core.run_guide._board_sort_key`). `RunGuideAnswer` performs no
   client-side sort or filter of this list — it trusts the order it's given.
   Each board card shows:
   - a **FIT badge** — `fit-badge fit-badge--{fit}` — with the label
     text from `FIT_LABEL` (`ideal` → "Ideal fit", `works` → "Works, with a
     tradeoff", `partial` → "Partial fit", `unconfirmed` → "Fit
     unconfirmed"). Note the dataset actually has four fit tiers, not three —
     `partial` sits between `works` and `unconfirmed` and isn't named in the
     three-way IDEAL/WORKS-WITH-A-TRADEOFF/UNCONFIRMED shorthand but exists
     in code and CSS.
   - a `TrustTierBadge` for the recipe's `status` (known-good/reported/
     unverified/broken) and the `chip_family`, when present.
   - grounded reasons + particularities (`board.reasons` concatenated with
     `board.particularities`), rendered only if either list is non-empty.
   - an optional `note` — the one LLM-contributed sentence, already
     grounding-validated server side.
   - a **source link** — only `board.sources[0]`, rendered as a real
     `TrackedLink`, never auto-followed.
7. **"See the full `<firmware>` page ›"** — a secondary, always-a-click
   `<Link>` in `HomeView`, never an auto-redirect. The full firmware page
   (with `RecipeGroupList`, etc.) stays one click away.

## Component reference

### RunGuideAnswer.tsx

- **Purpose:** renders the grounded `run_guide()` answer inline on the home
  intent box.
- **Appears in:** `HomeView.tsx`, inside the `parse.kind === "firmware"`
  branch, as `<RunGuideAnswer guide={guide} />`.
- **Consumes:** the full `RunGuideResponse` — `firmware_name`, `summary`,
  `requires`, `not_required`, `boards[]` (`fit`, `reasons`,
  `particularities`, `status`, `chip_family`, `note`, `sources`),
  `excluded_boards`. It does **not** render `flash_next`, `citations`,
  `requirements` (the flattened label list), or a board's per-entry
  `requires`/`not_required` teaching (those exist on `RunGuideBoard` but stay
  unused here today).
- **Behaviour rules:**
  - Empty board list renders an explicit `"No boards recorded for this
    firmware yet."` state, never a blank section.
  - Boards render in `guide.boards` array order — **no client-side sort**;
    the API is the single source of truth for fit-ordering (see run-guide
    anatomy §6 above). If a future change needs a different on-screen order
    than the API provides, that's a backend change to
    `run_guide._board_sort_key`, not a frontend `.sort()`.
  - Only the first source per board is linked; there's no "show all sources"
    affordance today.
  - `excluded_boards` (present when a chip-family constraint filtered boards
    out) renders as a trailing note, only when non-empty.

### IntentPrompt.tsx

- **Purpose:** the free-text "what do you want to build/run" input that
  drives the home page's soft-entry flow.
- **Appears in:** `HomeView.tsx`, top of the intent box.
- **Consumes:** no API data — a pure controlled input.
  `{ onSubmit: (text: string) => void; loading: boolean }`.
- **Behaviour rules:**
  - Submits only a trimmed, non-empty string; whitespace-only input is
    silently swallowed (the only "validation" here, and it's a UI nicety,
    not business logic — the actual parse/search decision happens server
    side via `parseIntent`).
  - Submit button disabled while `loading`, label toggles
    "Searching…" / "Go".
  - No error state, no result rendering of its own.

### HomeView.tsx

- **Purpose:** the intent-first home page shell. Owns the parse state
  machine (firmware run-guide vs. wizard filters vs. keyword-search
  fallback), renders the "Understood" feedback, and composes
  `IntentPrompt`, `ResultsPanel`, `RunGuideAnswer`, `ExamplesGrid`, and the
  spec-wizard drawer.
- **Appears in:** `app/page.tsx`.
- **Consumes:** `parseIntent(text)` → `IntentParse` (`kind`, `understood`,
  `unmapped`, `firmware`/`firmware_name`), `runGuide(firmwareId)` →
  `RunGuideResponse`, plus `useExplorer()` state for the search/wizard path.
- **Behaviour rules (the intent state machine):**
  - `kind === "firmware"` with a resolved `firmware` id → loads the run
    guide and returns early. Comment in the code states the intent
    explicitly: *"Answer inline, grounded against the recipe graph. The full
    firmware page stays one click away, never automatic."*
  - `kind === "filters"` → routes into the existing wizard/search flow.
  - `kind === "unreadable"`, or `parseIntent` itself throws (model
    unreachable/rate-limited) → falls back to plain keyword search, and says
    so in the UI rather than presenting a keyword dump as understood intent.
  - Run-guide branch has three mutually exclusive states: loading
    (`"Working out why…"`), error (`"The API did not answer"` +
    the raw error message + a retry hint), and success (`RunGuideAnswer`).
  - The "Understood" block (see below) and the "See the full `<firmware>`
    page ›" link both live here, not inside `RunGuideAnswer`.

### The "Understood" intent-parse block

Not a separate component — it's markup inside `HomeView.tsx`, gated on
`parse` being present and having something worth reporting
(`understood.length > 0 || unmapped.length > 0 || kind === "unreadable"`).

- **Consumes:** `IntentParse.understood: string[]`,
  `IntentParse.unmapped: string[]`, `IntentParse.kind`.
- **Behaviour rules:**
  - Each `understood` string renders as an individual accent chip
    (`chip chip--accent`), keyed by its own text.
  - `kind === "unreadable"` renders a caveat: *"I couldn't read that as a
    build goal, so these are keyword matches instead."*
  - Non-empty `unmapped` renders a second, independent caveat: *"No field
    for `<fields>` in the atlas yet — results don't account for that."* Both
    caveats can appear together; neither implies the other.
  - `aria-live="polite"` so the parse result is announced on change.

### ResultsPanel.tsx

- **Purpose:** search/wizard results list — empty-start state with example
  chips, loading, error, zero-results-with-relax-chips, and the results list
  itself.
- **Appears in:** `HomeView.tsx` and `ExplorerView.tsx`.
- **Consumes:** `ExplorerState` (`results`, `loading`, `error`, `lastQuery`),
  plus `onExample`/`onRelax`/`onClear` callbacks.
- **Behaviour rules:**
  - Four states, mutually exclusive by `lastQuery`/`loading`/`error`/
    `results`: empty-start (before any query), loading, error, and
    results-present (which itself branches on `results.length === 0` for a
    "no matches, try dropping a filter" state).
  - Empty-start example chips: firmware-kind examples are real links to the
    firmware page; needs-kind examples are buttons that call `onExample` —
    both share `.chip.chip--button` styling so they read identically despite
    being different elements.
  - `results.map(...)` renders in exactly the order the API returned —
    **no client-side sort/filter**, same discipline as `RunGuideAnswer`.
  - Zero-results state offers "Drop `<filter>`" buttons per active filter
    chip, each calling `onRelax(chip.key)` — a UI convenience over an
    already-server-decided filter set, not a new filtering decision made in
    the frontend.

### PartResultCard.tsx

- **Purpose:** one-row card for a part (SoC/module/board) in a results list,
  optionally annotated with why it matched a wizard query or a firmware
  recipe.
- **Appears in:** `ResultsPanel.tsx`, `app/brands/[brand]/page.tsx`,
  `part/SocHub.tsx`.
- **Consumes:** `part: PartRecord | WizardRecord` (duck-typed via `"reasons"
  in part`, not a separate prop flag), `origin`, `position` (analytics only),
  optional `boardReason: BoardReason` (`board`, `status`, `chip_family`,
  `sources`, `reason`).
- **Behaviour rules:**
  - Spec chips (`specChips(part)`) render "on" specs in ink (`--fg`) and
    "off" specs muted — a data-driven true/false flag per chip, not a fixed
    visual rule.
  - Wizard-match reasons (`wizardPart.reasons`) and a firmware board-reason
    (`boardReason`) are independent, both optional, both render only when
    present — never combined or deduped against each other.
  - Board-reason line pairs a `TrustTierBadge` with the chip-family match and
    optional cited source (first source only, linked, never auto-followed).
  - Title click fires an analytics `track("result_click", …)` but does not
    itself perform navigation — the `<Link>` does that.

### ExamplesGrid.tsx

- **Purpose:** the three home "shelves" (Run a firmware / Build a project /
  Just show me) of example cards.
- **Appears in:** `HomeView.tsx`, below the results/run-guide area.
- **Consumes:** `examples: Example[]` (`FirmwareExample | NeedsExample`),
  each carrying its own `group` id from the API.
- **Behaviour rules:**
  - Shelf membership (`group`) is decided by the API, never recomputed
    here — the component only names the three shelf ids/titles/hints and
    filters examples into them.
  - No examples at all → renders nothing (`return null`). A shelf with zero
    matching examples in it → that shelf renders nothing too, no "no
    examples" placeholder.
  - Every card is a real link (firmware or needs kind); every subtitle comes
    from `explainNeeds()`/the API's own fields — never a generated claim
    about why a board is good.
  - Example order within a shelf is whatever order the API returned
    (`.filter()` preserves it) — no re-sort.

### TrustTierBadge.tsx

- **Purpose:** the shared "honesty layer" badge — colour dot + the tier word
  itself — for a recipe's trust tier.
- **Appears in:** `RunGuideAnswer.tsx` (board status), `PartResultCard.tsx`
  (board-reason status), `RecipeGroupList.tsx` (per-row recipe status).
- **Consumes:** `status: string` (`known-good` / `reported` / `unverified` /
  `broken`, or any other string).
- **Behaviour rules:**
  - `RECIPE_TIER_LABEL[status] ?? status` — an unrecognised status still
    renders its raw value, never silently disappears.
  - Colour is never the only signal: the word is always present alongside
    the dot (`--ok`/`--warn`/`--muted`/`--danger` respectively, `broken`
    additionally strikes through).
  - No tooltip, no interactivity — purely presentational.

### RecipeGroupList.tsx

- **Purpose:** board↔firmware recipe rows grouped by trust tier, used on
  both board pages (grouped by firmware) and firmware pages (grouped by
  board). Informational only — no flash affordance.
- **Appears in:** `app/firmware/[id]/page.tsx`, `part/BoardFirmware.tsx`.
- **Consumes:** `rows: RecipeRow[]` (`{ recipe, href, name, meta? }`).
- **Behaviour rules:**
  - This is the one list component that **does** re-bucket its input: rows
    are grouped into `known-good → reported → unverified → broken` (fixed
    order, `RECIPE_TIER_ORDER`), with any non-standard status collected into
    a trailing "other" group. This is a deliberate exception to the
    "render in API order" rule elsewhere — trust-tier grouping is the whole
    point of this component.
  - Within a tier, row order is preserved from the input array — no
    secondary sort by name/date/anything else.
  - Each row shows a `TrustTierBadge`, optional `meta`, and an optional
    flash-method label marked `title="…informational only"` — there is no
    click handler that triggers a flash from this list.

### FirmwareCard.tsx

- **Purpose:** card for a firmware record in a list — the firmware-page
  analogue of `PartResultCard`.
- **Appears in:** `app/firmware/page.tsx`.
- **Consumes:** `firmware: Firmware` (`id`, `name`, `category`,
  `maintainer`, `capabilities`, `socs`, …).
- **Behaviour rules:**
  - Chips are `capabilities` then `socs`, concatenated with no dedup or
    sort — capabilities always render emphasized (`spec-chip--on`), socs
    always render muted; this is a fixed visual distinction, not a
    data-driven per-chip flag like `PartResultCard`'s `specChips`.
  - No click analytics (`track()` is not called here, unlike every other
    card component) — worth fixing consistently if/when this file is
    revisited, not something to copy into new cards.

## Fit-ordering rule (backend-enforced)

`run_guide()`'s `boards[]` is sorted best-fit-first before the frontend ever
sees it: `ideal` (0) < `works`/`works-with-tradeoff` (1) < `unconfirmed` (2)
< any other/unsupported value (last), with a stable secondary sort of
known-good status before other statuses, then board display name A→Z. See
`esp_atlas_core.run_guide._board_sort_key` and the pinned assertions in
`apps/core/tests/test_coverage_matrix.py` (`test_bruce_ideal_boards_all_rank_before_works_boards`,
`test_launcher_unconfirmed_board_is_last`,
`test_board_fit_rank_sequence_is_non_decreasing`). `RunGuideAnswer` trusts
this order completely and must never re-sort `guide.boards` itself — if the
on-screen order ever needs to change, change the backend rank function, not
the component.
