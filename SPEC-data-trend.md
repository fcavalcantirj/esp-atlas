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
