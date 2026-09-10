# SPEC — Data-Quality Trend (Jr's daily gauge history)

> **The gauge tells you where you are; the trend tells you where you're going.** A single
> completion % (SPEC-data-completion.md) is a snapshot. This spec makes Jr record that snapshot
> once a day so the finite ground's *slope* — and the infinite ground's *volume* — are visible
> over time. (Extends SPEC-data-completion.md; 2026-09-09.)

## What this is (and is not)
- A **REPORT, never a gate.** Exactly like `scripts/data_completion.py`, this never affects
  `scripts/validate.py`'s exit code and never blocks a tick. It only writes docs.
- It **REUSES** `compute_completion(data_dir)` for every finite number. It does NOT recompute
  presence/completeness. The only numbers it computes itself are the INFINITE-ground *volumes*
  the gauge deliberately omits (firmware + recipe counts), because SPEC-data-completion.md leaves
  the infinite ground unmeasured — but its *volume and coverage* are still worth trending.
- It lives in `jr/data_snapshot.py` (tick-owned, so the `jr-tests` job covers it), separate from
  `jr/telemetry.py` (the GA4/GSC traffic job). The two never mix.

## The trend row (one JSON object per day)
`build_row(data_dir, date_str)` returns a flat, JSON-serialisable dict:

| field | source | meaning |
|-------|--------|---------|
| `date` | injected `date_str` (`YYYY-MM-DD`) | the day this row measures |
| `finite_overall_pct` | `compute_completion` `overall_pct` | the board-weighted finite gauge |
| `boards_pct` / `socs_pct` / `modules_pct` / `brands_pct` | `entities[e].pct` | per-entity finite completion |
| `board_fields` | `entities.boards.per_field` | `{count, pct}` for the four First-Flash keys `usb_serial`, `getting_started`, `download_mode`, `pinout` — pulled straight from the gauge, never rescanned |
| `firmware_count` | count of `data/firmware/*/firmware.md` | INFINITE-ground volume |
| `recipe_count` | count of `data/recipes/*/recipe.md` | INFINITE-ground volume |
| `compat_density` | `round(recipe_count / firmware_count, 2)` (0.0 if no firmware) | mean boards mapped per firmware — the SPINE coverage signal |
| `boards_with_firmware` | distinct `<board>` in `data/recipes/<board>__<firmware>/` dir names | boards reachable from ≥1 recipe |
| `boards_zero_firmware` | `boards_total − boards_with_firmware` | boards no recipe maps yet |
| `top_gap` | lowest-% finite field with records, from `compute_completion` `gaps` | `"<entity>.<field> <pct>%"` |

`build_row` is **pure and deterministic**: it takes an explicit `date_str` and never reads the
clock, so it is testable with an injected date.

## The two output files
`write_snapshot(repo_root, date_str)` writes BOTH, under `docs/telemetry/`, and returns
`(row, delta)` — `delta` is the diff vs the immediately-prior row, or `None` on the first snapshot.

1. **`docs/telemetry/data-trend.jsonl`** — the append-only history. One compact JSON object
   (the row above) per line, **sorted by `date` ascending**. Written by: read the existing
   file, DROP any row whose `date` equals `date_str`, append this row, re-sort, rewrite.
   **Idempotent by date:** running twice for the same date yields byte-identical file content.
2. **`docs/telemetry/data-<date_str>.md`** — the human snapshot for that day: the
   `compute_completion` report text (rendered via its own `print_report`), followed by a
   `## Δ since <prev-date>` block computed against the immediately-prior row in the jsonl.
   The block shows deltas for `finite_overall_pct`, each of the four board fields' counts,
   `firmware_count`, `recipe_count` and `compat_density`. With no prior row it reads
   `first snapshot — no baseline`.

## Idempotency & determinism
- Same `(repo_root, date_str)` + same data ⇒ identical files, every run.
- A second tick the same day just rewrites that date's row; git sees no diff unless a count
  actually changed (no spurious churn).
- The clock is confined to the CLI `main`: the core functions take `date_str` explicitly.

## Tick integration
`run_tick` calls `write_snapshot(root, <today>)` on **non-dry-run only**, after the gauge, in the
same block that writes memory/ledger. It is **best-effort**: wrapped in try/except that appends a
warning to `r.warnings` on failure and NEVER aborts the tick (matching the hydrate step). The two
written paths are added to the set the tick commits/publishes, and the returned row + delta are
stored on the report so the PR body carries one data-delta line. A **dry-run writes nothing.**

## CLI
`python3 jr/data_snapshot.py --repo-root . --date 2026-09-09` (default `--date` = today, UTC).
Mirrors `scripts/data_completion.py`'s argparse style; the clock lives only here.

---

# v2 — Full-field coverage + staleness (2026-09-10)

> **Motivation (measured, not assumed).** `compute_completion` computes a `{count, pct}` for
> **every** finite field of **every** entity each tick (`entities[e].per_field`). The v1 row
> persisted only four of them (`board_fields`), so ~13 field metrics were computed and thrown
> away every tick. That made real blind spots invisible in the series — e.g. `boards.images`
> (18.9%), `boards.pinout` (16.7%), `modules.psram` (16.7%): near the floor, never trended.
> v2 records **everything the gauge already computes** (no new measurement), and adds a
> **staleness verdict** so each metric reads *improving / flat / stale* instead of a bare number.
>
> Still a **REPORT, never a gate.** Still reuses `compute_completion` for every finite number —
> v2 adds no new scan; it stops discarding what the gauge produces, and derives judgments from the
> recorded history. Facts are stored; verdicts are derived (recomputable from the jsonl alone).

## v2.a — `entity_fields`: record every per-field metric
The trend row gains one additive key. `board_fields` is **unchanged** (the four First-Flash
headline keys, for Δ-block and back-compat continuity with existing rows).

| field | source | meaning |
|-------|--------|---------|
| `entity_fields` | `entities[e].per_field` for **every** entity `e` | `{ "<entity>": { "<field>": {"count", "pct"}, ... }, ... }` for boards (all 8), socs (5), modules (5), brands (1+) — pulled straight from the gauge, never rescanned |

- Order within each entity follows `data_completion.FIELD_SPECS` (report order), so the jsonl is
  stable and diffs are readable.
- Additive & back-compatible: existing rows lack `entity_fields`; readers/`compute_delta` treat a
  missing key as `{}` (no crash, no phantom deltas). The two historical rows are left as-is.
- `board_fields` values remain a subset of `entity_fields["boards"]` — intentional redundancy so
  the v1 Δ block and any existing consumer keep working untouched.

## v2.b — staleness verdict (derived, not stored)
A judgment layer over the recorded history — **not** a new row field (rows stay raw facts;
verdicts are always recomputable from the jsonl). New pure helper:

`field_momentum(rows, window=DEFAULT_WINDOW)` → `{ "<entity>.<field>": {"status", "delta_window", "since"} }`

For each finite field present in the latest row, compare its `count` to the same field's `count`
in the row `window` snapshots back (or the earliest available if history is shorter):
- **`improving`** — count increased over the window (`delta_window > 0`).
- **`declining`** — count decreased (`delta_window < 0`) — surfaces silent data loss/removal.
- **`flat`** — no change, but fewer than `window` snapshots of history exist yet (too soon to judge).
- **`stale`** — no change across a **full** `window` of consecutive snapshots. This is the signal
  v1 could not express: a field stuck for `window` ticks reads `stale`, not a repeated "0 delta".

`DEFAULT_WINDOW` = 7 snapshots. Pure and deterministic (no clock; operates on the passed rows).

## v2.c — markdown surfacing
`data-<date>.md` gains a **`## Field coverage`** section after the Δ block: one line per entity
field, `"<entity>.<field>: <count> (<pct>%) — <status>"`, ordered worst-pct first so the floor
(images, pinout, psram) is at the top of the human eye. `stale` and `declining` fields are marked
so a metric that isn't moving is obvious at a glance. The v1 Δ block is unchanged.

## v2 — what stays out of scope (roadmap, separate specs)
These are *important-and-not-computed* but each needs its own measurement (not just recording what
the gauge emits), so they are **not** in v2 and will be specced/built one at a time after it:

- **Citation completeness** (Tier 2). `data_completion` v1 measures *presence only* — a field is
  "complete" when non-empty, regardless of whether it's sourced. A present-but-uncited field is
  invisible. Needs a cite-or-omit gauge; own spec.
- **Infinite-ground depth** (Tier 2). Firmware/recipes are trended by *count* only. Whether each
  firmware entry is *complete* (description, flash steps, board coverage) is unmeasured. Needs a
  depth gauge for the infinite ground; own spec.
- **Entry freshness** (Tier 2). No per-entry "last-verified" age trend — can't tell if catalog
  data is going stale as upstream firmware moves on. Needs a recency field + gauge; own spec.
- **Demand-closure & per-page attribution** (Tier 3). Whether the data actually earns SEO —
  UNCOVERED-backlog trend, RANKS_POORLY position movement, per-page traffic. Lives in
  `jr/telemetry.py` (GA4/GSC), depends on that digest committing; own spec, separate track.
