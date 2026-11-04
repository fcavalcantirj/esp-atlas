"""EspAtlas Jr — Track A (finite backfill) tick stage. SPEC-data-completion.md.

Track A per the allocation law is the FINITE backfill: fill missing, cited board fields
(First-Flash download_mode/usb_serial, getting-started, …) so the finite ground climbs
toward 100% — the only work that moves the boards-completion gauge.

This wraps board_backfill.backfill_board over the Espressif worklist, writing grounded
fields INTO THE WORKTREE (ctx.root) and returning a tick.StageResult. It never opens its
own PR — the tick opens the single PR from every stage's paths (board_backfill.py's own
main()/open_backfill_pr() is the standalone manual lane; the stage reuses only its pure
per-board writer).

Budget = boards ATTEMPTED; "complete" boards cost no fetch and don't count. A board on which
every source failed (status "skipped") is cooled down for board_cooldown.COOLDOWN_DAYS
(jr/board_cooldown.json, shipped with the tick): while cooling it is passed over for free, so
the budget moves to boards that can still be filled. Each skip line names its per-field
reasons, vendor/manifest/boards_txt (no_pattern_match, field_absent, doc_unreachable,
no_manifest, no_board_key, corroboration_only, conflicts, needs_review).

The PlatformIO manifest and boards.txt are corroboration only (owner mandate G3,
jr/board_corroboration.py): every board line carries what they said, with their pinned citations.
A board whose vendor usb_serial conflicts with them is not written; the stage flags needs_human
(auto-merge withheld) and cools the board down so the same conflict is not re-flagged hourly.

Dry-run (ctx.dry_run): every board is grounded exactly as for real, but no board.md and no
cooldown is written; each would-be write is returned in StageResult.would_write instead
(`{"path", "field", "value"}`), so the tick report shows what a real run would do.
"""
from __future__ import annotations

import board_backfill
import board_cooldown
import board_corroboration

DEFAULT_BUDGET = 4
CALLS_PER_BOARD = 3        # the vendor user guide + the PlatformIO manifest + boards.txt
SECONDS_PER_BOARD = 30.0   # three fetches (boards.txt is ~3 MB) + parse
# Skips where every source was actually tried and failed, or the board's usb_serial conflicts with
# a pinned toolchain source (re-fetching cannot change that; a human resolves it). A no-soc skip
# fetched nothing: it is fixed by editing the record, so it must not wait out a cooldown.
COOLDOWN_REASONS = ("doc-unreachable", "nothing-groundable", "needs-review")


def run(ctx, budget: int = DEFAULT_BUDGET, fetch=None):
    import tick
    today = ctx.now.strftime("%Y-%m-%d")
    fetch = ctx.budget.wrap(fetch or board_backfill.default_fetch, "https")
    data_root = ctx.root / "data"
    boards_dir = data_root / "boards"

    # Feed EVERY board whose brand has a REGISTERED vendor doc resolver — not just Espressif.
    # The tick must cover all vendors board_backfill knows how to ground (Espressif, m5stack,
    # …); the old espressif-only glob left every other vendor's coverage stuck at 0. A brand
    # with no registered resolver is left out entirely (backfill_board would skip it anyway).
    # Sort by the repo-relative path string so the order is stable across ticks and the
    # hour-rotation below stays deterministic.
    boards = sorted(
        (p for brand in board_backfill.VENDOR_DOC_RESOLVERS
         for p in (boards_dir / brand).glob("*/board.md")),
        key=lambda p: str(p.relative_to(ctx.root)),
    )
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

    cooldown_path = ctx.root / board_cooldown.RELPATH
    cooldown = board_cooldown.load(cooldown_path)
    paths, would_write, lines, filled, skipped, attempted, cooling, cooled = [], [], [], 0, 0, 0, 0, 0
    needs_human = False
    for path in boards:
        if attempted >= budget:
            break
        if board_cooldown.is_cooling(cooldown, path.parent.name, ctx.now):
            cooling += 1
            continue  # every source failed for it recently; no fetch spent
        if ctx.budget.remaining_calls() < CALLS_PER_BOARD or ctx.budget.remaining_seconds() < SECONDS_PER_BOARD:
            lines.append(f"stopped: tick budget low ({ctx.budget.remaining_calls()} calls left)")
            break
        entry = board_backfill.backfill_board(path, data_root, fetch, today, write=not ctx.dry_run)
        status = entry["status"]
        if status == "complete":
            continue  # not on the worklist; no fetch spent
        attempted += 1
        if status == "backfilled":
            rel = str(path.relative_to(ctx.root))
            if ctx.dry_run:
                values = entry.get("values") or {}
                would_write += [{"path": rel, "field": f, "value": values.get(f)} for f in entry["written"]]
            else:
                paths.append(rel)
            filled += 1
            note = f"{entry['board_id']}: {'would ' if ctx.dry_run else ''}+{'+'.join(entry['written'])}"
            if entry.get("omitted"):
                note += f" (omitted {','.join(entry['omitted'])})"
            lines.append(_with_corroboration(note, entry))
        else:
            skipped += 1
            lines.append(_with_corroboration(_skip_line(entry), entry))
        if entry.get("needs_review"):
            needs_human = True
        if entry.get("needs_review") or entry.get("reason") in COOLDOWN_REASONS:
            reason = entry.get("reason") or "needs-review"
            board_cooldown.record(cooldown, path.parent.name, reason,
                                  entry.get("field_reasons") or {}, now=ctx.now)
            if ctx.dry_run:
                would_write.append({"path": board_cooldown.RELPATH, "field": f"by_board.{path.parent.name}",
                                    "value": reason})
            cooled += 1

    if cooled and not ctx.dry_run:
        board_cooldown.save(cooldown, cooldown_path, now=ctx.now)
        paths.append(board_cooldown.RELPATH)

    verb = "would backfill" if ctx.dry_run else "backfilled"
    summary = f"{verb} {filled}, skipped {skipped}"
    if cooled:
        summary += f", {'would cool' if ctx.dry_run else 'cooled'} {cooled} for {board_cooldown.COOLDOWN_DAYS}d"
    if cooling:
        summary += f", cooling {cooling}"
    if lines:
        summary += " · " + "; ".join(lines)
    return tick.StageResult("backfill", paths=paths, summary=summary, needs_human=needs_human,
                            would_write=would_write)


def _with_corroboration(line: str, entry: dict) -> str:
    """The board's line plus what the toolchain sources said, each with its citation."""
    notes = board_corroboration.describe(entry.get("corroboration") or {})
    return f"{line} · {' · '.join(notes)}" if notes else line


def _skip_line(entry: dict) -> str:
    """`<board>: skip <reason> [field=vendor/manifest/boards_txt, ...]` — why each missing field
    stayed empty."""
    line = f"{entry['board_id']}: skip {entry.get('reason', '')}"
    reasons = entry.get("field_reasons") or {}
    if reasons:
        parts = [f"{field}={'/'.join(by_source.values())}" for field, by_source in reasons.items()]
        line += f" [{', '.join(parts)}]"
    return line
