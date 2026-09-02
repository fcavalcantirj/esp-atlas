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

1. **Fork → source.** GitHub `.fork`/`.source`; walk to the network root. Author the **canonical
   original**, never a downstream fork. *(jr/forks.py)*
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

## Drain output model — DECISION NEEDED

With admission clean-by-construction, the drain no longer needs an LLM reviewer. Two options:

- **(A) Direct-to-main:** drain commits admitted entries straight to `main` (auto-deploys). Simplest,
  fewest parts.
- **(B) PR + CI-green auto-merge:** drain opens a PR; `validate.py` CI runs; auto-merge on green.
  **No LLM in the loop.** One safety checkpoint, still few parts.

**Recommend (B)** — keeps a mechanical gate (CI) and an audit trail without the LLM review cron.

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
3. **Wire the 4 gates into drain admission**; **delete `jr-review-merge`**; set drain output to
   option (B).
4. **Verify** with a dry-run drain: a fork / sub-floor / dup / banner-title candidate is rejected or
   transformed at admission.

## Acceptance

- Given a fork, sub-floor repo, duplicate, or banner-title candidate, the drain **rejects or
  transforms it at admission** (covered by tests).
- **No `jr-review-merge` cron.** `validate.py` enforces the floor.
- Catalog invariant: **0 forks** (all resolved to originals), **0 sub-floor**, **0 dups**, **0 banner
  titles** — and it stays that way without downstream cleanup.

## Open question — is Jr worth keeping at all?

If a clean-by-construction drain still isn't worth the upkeep for a ~70-entry catalog, the honest
alternative is to **retire Jr and curate manually**. Decide after step 4: if admission is truly
low-maintenance, keep it; if it still needs babysitting, kill it.
