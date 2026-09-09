"""EspAtlas Jr — Track A (finite backfill) tick stage. SPEC-data-completion.md.

Track A per the allocation law is the FINITE backfill: fill missing, cited board fields
(First-Flash download_mode/usb_serial, getting-started, …) so the finite ground climbs
toward 100% — the only work that moves the boards-completion gauge.

This wraps board_backfill.backfill_board over the Espressif worklist, writing grounded
fields INTO THE WORKTREE (ctx.root) and returning a tick.StageResult. It never opens its
own PR — the tick opens the single PR from every stage's paths (board_backfill.py's own
main()/open_backfill_pr() is the standalone manual lane; the stage reuses only its pure
per-board writer).

Budget = boards ATTEMPTED (a fetch each); "complete" boards cost no fetch and don't count.
Known limit (follow-up): a doc-unreachable board is retried each tick (no skip-cache yet),
so a run of unreachable boards can consume the budget before a fillable one — bounded by
the tick's own call budget.
"""
from __future__ import annotations

import board_backfill

DEFAULT_BUDGET = 4
CALLS_PER_BOARD = 1
SECONDS_PER_BOARD = 20.0   # one user-guide fetch + parse


def run(ctx, budget: int = DEFAULT_BUDGET, fetch=None):
    import tick
    today = ctx.now.strftime("%Y-%m-%d")
    fetch = ctx.budget.wrap(fetch or board_backfill.default_fetch, "https")
    data_root = ctx.root / "data"
    esp = data_root / "boards" / "espressif"

    boards = sorted(esp.glob("*/board.md"))
    # ROTATE the start each tick so the worklist ADVANCES instead of re-hitting the same
    # first-N boards every hour (which left backfill stuck on a few un-groundable boards and
    # never progressing). Deterministic + stateless — no skip-cache file, so no churny
    # cache-only PRs. Consecutive hourly ticks cover disjoint windows: full coverage every
    # ceil(N/budget) ticks; a genuinely un-groundable board is retried only once per cycle.
    n = len(boards)
    if n:
        hour_index = ctx.now.toordinal() * 24 + ctx.now.hour
        start = (hour_index * max(1, budget)) % n
        boards = boards[start:] + boards[:start]

    paths, lines, filled, skipped, attempted = [], [], 0, 0, 0
    for path in boards:
        if attempted >= budget:
            break
        if ctx.budget.remaining_calls() < CALLS_PER_BOARD or ctx.budget.remaining_seconds() < SECONDS_PER_BOARD:
            lines.append(f"stopped: tick budget low ({ctx.budget.remaining_calls()} calls left)")
            break
        entry = board_backfill.backfill_board(path, data_root, fetch, today)
        status = entry["status"]
        if status == "complete":
            continue  # not on the worklist; no fetch spent
        attempted += 1
        if status == "backfilled":
            paths.append(str(path.relative_to(ctx.root)))
            filled += 1
            note = f"{entry['board_id']}: +{'+'.join(entry['written'])}"
            if entry.get("omitted"):
                note += f" (omitted {','.join(entry['omitted'])})"
            lines.append(note)
        else:
            skipped += 1
            lines.append(f"{entry['board_id']}: skip {entry.get('reason', '')}")

    summary = f"backfilled {filled}, skipped {skipped}"
    if lines:
        summary += " · " + "; ".join(lines)
    return tick.StageResult("backfill", paths=paths, summary=summary)
