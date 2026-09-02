# SPEC — Firmware coverage → real-world verification (no hand-curation)

> `test_every_firmware_has_a_run_case` requires a **hand-authored** coverage-matrix case per
> firmware. Fine for a few curated ones; **impossible** now that Jr adds 40+ autonomously — it
> reds CI on every batch. Kill the hand-curation gate; replace "coverage" with truth from *usage*.
> (Felipe, 2026-09-02: "a new matrix asking for hand curation? impossible. I tried the firmware
> on board, didn't work — we need a space to check this.")

## Phase 1 — kill hand-curation, add the verification space (CI green tonight)

### Remove the per-firmware hand-case gate
- **Delete** `test_every_firmware_has_a_run_case` (the "every seeded firmware needs a RUN_MATRIX
  case" assertion).
- **Keep** the curated `RUN_MATRIX` as a *characterization* subset (diverse firmware kinds) — it
  no longer has to cover every firmware; `test_run_matrix_firmware_ids_are_real` stays.
- **No auto "it works" assertion** — code can't know if firmware actually runs on hardware.

### The verification space lives on the RECIPE
A recipe **is** a firmware×board pairing, so "did it work" is a fact about that pairing:
`data/recipes/<board>__<firmware>/recipe.md` frontmatter:
```yaml
tested:
  status: works | broken | untested     # default: untested when absent
  via: website-flash | physical | report
  as_of: YYYY-MM-DD
  note: "e.g. README claims C5 support; real flash bricked / no boot / worked fine"
```
- Optional in `schema/recipe.schema.json` (absent ⇒ untested).
- **User-visible** — the flash panel renders ✓ verified-working / ⚠ reported-broken.
- **Self-writing** — the website flash flow and physical tries write it (the First-Flash loop
  feeds it; e.g. the C5 J5-jumper find is a `broken`+note).

### The replacement test (loud gaps, zero hand-curation)
- A recipe may be `status: broken` **only with a `note`** (a broken combo must say why — the gap
  stays loud, ROADMAP-style, never papered over).
- New firmware **never** needs a hand case. That's the whole win.

## Phase 1b — verification is PERISHABLE and dated (the `as_of` heartbeat)

> Felipe, 2026-09-02: "if someone flashes successfully via website, will it update the timestamp?
> it should, always, right? because it can also stop working."

Yes — always. `known-good` is really **known-good *as of* a date**, exactly like the popularity
`as_of` snapshot. A recipe that flashes today can regress when the firmware ships a new release,
a new silicon revision arrives (the C5 rev-v1.2 story), or the browser flasher changes. So the
recipe's `verified_at` is a **freshness heartbeat**, not a one-time stamp:

- **Every successful flash → refresh `verified_at` to today.** Confirms "still works as of today."
  Fresh verification outranks stale; a `known-good` last confirmed months ago is a soft gap that
  surfaces on a **re-verify worklist** (same shape as the popularity-refresh job).
- **A failed flash of a recipe that claims it works → records a dated failure signal**, which can
  flip `status` toward `broken` **with a `note`** (guarded by `test_no_broken_recipe_without_a_reason`).
  That is the "space to mark the one that didn't work."

**Mechanics (the honest constraint).** The website runs on Vercel serverless — read-only FS, it
**cannot** commit to git, so it must never rewrite catalog truth directly. The loop:
1. The flash flow emits a **dated flash-result event** (success/failure + chip rev + firmware
   version + esptool-js/browser), cited by that event.
2. **Jr** (the bot, which has repo write in CI/cron) aggregates events → opens a **PR** bumping
   `verified_at` / `status` / `notes`. Human merges (JR Law 3 — bot proposes, human disposes).

Everything stays git-tracked and cited; the citation for a website verification is the flash
event itself. Build order: the Jr-side write-back (data + PR) is normal latitude; the website
**emit** touches `apps/web` and ships only with Felipe's explicit OK.

## Phase 2 — routing precision (fixes the wifi6 hijack + the unroutable 3)
Intent routing = deterministic firmware **name-match** OR LLM→**allowlisted filters**. The
name-match is imprecise both directions:
- **Too greedy:** "a wifi 6 board" matches a firmware whose *name* contains "wifi" → hijacks the
  `radio: wifi-6` filter. **Fix:** a **capability vocabulary** (wifi-6, wifi, lora, zigbee, ble,
  thread, matter, sub-ghz, 5ghz, ethernet…) present in a query **forces the filter path**, never
  overridable by a firmware-name match.
- **Too weak:** `m5gotchi` / `meowusb-ble` / `space-clock` don't route to their own names.
  **Fix:** tighten name-matching so a firmware's distinctive name routes to *it*, without generic
  tokens leaking.

## Order (Felipe: coverage first)
1. **Phase 1** — remove the gate + recipe `tested` field + replacement test → **CI green**.
2. **Phase 2** — routing precision → resolves the wifi6 hijack + the 3 unroutable names.
