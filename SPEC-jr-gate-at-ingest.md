# SPEC — Jr refactor: gate-at-ingest

> **Status:** planned, not built. Jr crons (`jr-drain`, `jr-review-merge`) are **PAUSED** as of
> 2026-09-02 pending this refactor. Live catalog is stable and untouched.

## Problem — why we're doing this

The Jr pipeline is **generate-then-clean**, and that is the flaw. The drain scrapes broadly and
**admits junk** — GitHub forks instead of the popular original, sub-floor repos, duplicates,
repo-status banner titles (`【Maintenance completed】…`). A whole **downstream apparatus** then exists
to mop it up: the `jr-review-merge` cron (category fixes + dup collapse + auto-merge), `validate.py`
in CI, and manual/agent firefighting.

It is always cheaper to **not ingest junk** than to ingest it and maintain machinery to clean it.
Evidence from a single day (2026-09-02): a 4★ fork cataloged instead of its 48★ original; an
AI-StackChan duplicate; a banner title; and — because the delegate and the drain **share one working
tree** — two **destructive collision PRs** (#100/#101) that would have deleted ~1,700 lines.

## Principle

**Quality is enforced at ADMISSION**, before a candidate becomes a PR or commit. Nothing enters the
catalog that is not already: fork-resolved, above floor, deduped, clean-titled. **The catalog is
clean by construction**, and the downstream cleanup layer is deleted.

## The ingest gate — ordered admission checks

For each scraped candidate, run in order; reject or transform *before* authoring. All four already
exist as verified logic (118 passing tests on the logic branch — see "Reuses" below):

1. **Fork → source (GUARDED — do NOT blindly jump to the GitHub parent).** If a candidate is a
   fork, consider its network root (`.source`). **Resolve ONLY when both hold: (a) source stars >
   fork stars, AND (b) it's the same project/platform** (not a divergent hard-fork, not a
   cross-platform parent). Otherwise **keep the fork** — it's either the more-popular entry or a
   meaningful platform-specific port. Evidence the guard is required (2026-09-02 sweep, 7 forks):
   ✅ resolve flipper→Sor3nt (425★), zx-spectrum→…-external (48★), sshclient→fernandofatech (67★);
   ⛔ keep anarch-cardputer (14★ > its 12★ ESPboy parent) and cardputer-mp3-adv (16★ > 7★ parent);
   ⛔ never resolve circuitpython→micropython (distinct project) or
   claude-desktop-buddy-cardputer→anthropics/claude-desktop-buddy (non-Cardputer parent).
   *(jr/forks.py — add this guard; the current resolver walks to root without it.)*
2. **Popularity floor.** Keep iff the resolved source has **stars ≥ 25 OR forks ≥ 25**. Downloads are
   **not** a metric anywhere. *(jr/scorer.py)*
3. **Dedup.** If the resolved source is already represented (by repo identity / id), skip.
4. **Title sanitize.** Strip status banners (`【…】`, WIP, DEPRECATED, `[test]`, …) from the name.
   *(jr/normalize.py — already shipped to main)*

Only candidates passing all four are authored.

## What gets DELETED

- **`jr-review-merge` cron** — its entire job (category fixes, dup collapse, guard check, auto-merge,
  the 🚀/⏸️/✅ status message) exists only to clean leaked junk. With gate-at-ingest there is nothing
  to fix → **remove the cron** and the emoji-status problem disappears with it.
- **The manual-merge / firefight flow.**
- **Kept:** `validate.py` (now also enforces the floor as a mechanical backstop), `jr-telemetry`.

## Drain output model — DECIDED: pull request + auto-merge on green

**Superseded 2026-09-03.** An earlier revision of this spec decided *direct-to-main*. Felipe
rejected that: it puts the Vercel deploy in front of any CI, and it makes
[`how-we-work`](apps/web/app/how-we-work/page.tsx)'s "it never writes to main" untrue.

The tick **opens a pull request** and then calls `gh pr merge --auto --squash`. CI decides; a human
may veto. *Bot proposes, CI disposes.* One squashed commit per tick, so a bad tick is a one-line
revert.

**Branch protection is not a nicety here — it IS the gate.** Verified on 2026-09-04: with no
protection configured, `gh pr merge --auto` does not queue, it merges **immediately**, because
auto-merge has no required checks to wait on. An unprotected repo therefore turns this model back
into direct-to-main under another name. `main` must require `schema`, `tests` and `jr-tests` before
the tick goes live, and the tick's preflight must fail red when protection is missing or its
required-check list is empty — not merely when auto-merge is switched off.

The publisher still self-validates before it pushes (`validate.py` once per tick, then the test
suite only if something was written), but that is now defence in depth rather than the only gate.

## One-time migration of the existing catalog

Run the tested `catalog_migrate` once: **strip downloads → resolve existing forks to originals →
purge still-sub-floor → `validate` green**. (e.g. zx-spectrum `internal` 4★ → `external` 48★; ~38
entries evaluated against the new floor.) Produce a diff for review **before** merge.

## Reuses existing verified work (not wasted)

The logic branch already holds, with **118 passing tests**:
`jr/forks.py` (resolver) · `jr/scorer.py` (floor) · `jr/catalog_migrate.py` + `scripts/strip_downloads.py`
(migration) · `jr/normalize.py` (sanitizer, already on main). The refactor **wires these into drain
admission and deletes the review cron** — it does not rebuild them.

## Build steps (small + sequenced — crons paused, so no collision, no timeouts)

1. **Land the logic** — rebase the logic branch on `main`; floor + fork-resolver + migration
   functions + `validate.py` floor-check. (Verify tests; the guard's "unparsable" glitch has
   false-FAILed clean runs — verify by running the suite directly.)
2. **Run the one-time migration** → diff → review → merge.
3. **Wire the 4 gates into drain admission**; **delete `jr-review-merge`**; set the tick's output
   to **pull request + `gh pr merge --auto --squash`** behind branch protection, keeping
   self-validate-before-push (`validate.py` green before the branch is pushed) as defence in depth.
4. **Verify** with a dry-run drain: a fork / sub-floor / dup / banner-title candidate is rejected or
   transformed at admission, and a red `validate.py` aborts the push.

## Acceptance

- Given a fork, sub-floor repo, duplicate, or banner-title candidate, the drain **rejects or
  transforms it at admission** (covered by tests).
- **No `jr-review-merge` cron.** `validate.py` enforces the floor.
- Catalog invariant: **0 forks** (all resolved to originals), **0 sub-floor**, **0 dups**, **0 banner
  titles** — and it stays that way without downstream cleanup.

## If it still needs babysitting → change / improve / recreate Jr

After step 4, judge by upkeep. If gate-at-ingest is genuinely low-maintenance, keep it. If it still
needs babysitting, **we iterate — change, improve, or recreate Jr** (not abandon it). Jr stays a
living system; the bar is that it earns its keep without firefighting.
