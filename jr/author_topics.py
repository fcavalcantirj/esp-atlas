"""EspAtlas Jr — one-shot GitHub-topics authoring driver (jr/author_topics.py).

Where jr/ingest_topics.py is the READ-ONLY sizing report for the GitHub-topics source
(jr/source_topics.py), this is the driver that actually ADMITS genuine firmware it surfaces into
the catalog — by handing it to jr/drain.py's run_drain(), the SAME deterministic pipeline the
launcher-catalog drain uses end to end (prefilter, score_candidates -> scorer.score_entry, rank,
cap_categories, author_selected, per-item guard, ledger). No scoring, authoring, or rollback logic
lives here — this module's only job is wiring: point run_drain's `fetch_catalog` at the topics
source instead of the launcher catalog, size the batch for a one-shot pass over the full topic
yield instead of an hourly tick's small batch, and wire the same live fork-to-canonical resolver
jr/drain.py's own __main__ uses.

max_per_category=8 / batch_size=40 (vs. drain's tick defaults of 4 / 20): a one-shot authoring
pass over source_topics.DEFAULT_TOPICS's yield is meant to admit everything that clears the gate
in one run, not dole it out in launcher-tick-sized slices.

    python3 author_topics.py                # real run: fetch topics, score, author, guard, print a report
    python3 author_topics.py --limit 10      # controlled first pass: at most 10 items authored
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import drain  # noqa: E402
import ledger  # noqa: E402
import source_topics  # noqa: E402

MAX_PER_CATEGORY = 8
BATCH_SIZE = 40


def _print_report(report: dict) -> None:
    print(f"fetched={report['fetched']} prefiltered={report['prefiltered']} "
         f"scored_clean={report['scored_clean']} skipped_scoring={report['skipped_scoring']} "
         f"selected={report['selected']} dropped_cap={report['dropped_cap']}")
    print(f"authored ({len(report['authored'])}): {report['authored']}")
    for d in report["dropped_guard"]:
        print(f"  dropped: {d['id']} — {d['reason']}")
    pop = report.get("skipped_popularity", [])
    print(f"skipped below-popularity-floor ({len(pop)}):")
    for s in pop:
        print(f"  {s['firmware_id']} — stars={s['stars']} forks={s['forks']}")
    print(f"guard ok={report['guard']['ok']}")


def main(limit: int | None = None, search_topic=None, fetch_meta=None, resolve_source=None,
        ledger_path=ledger.DEFAULT_LEDGER_PATH, today: str | None = None) -> dict:
    """Run drain.run_drain() end to end over the GitHub-topics source. `search_topic`,
    `fetch_meta`, and `resolve_source` are all injectable (default: the real, network-touching
    clients — search_topic falls back to source_topics.default_search_topic, fetch_meta to
    drain.default_fetch_meta, resolve_source to drain's own `_live_resolve_canonical`, the SAME
    live gh-based fork-to-canonical resolver jr/drain.py's __main__ wires) so tests make no
    network call while a real run stays wired to the live pipeline. `limit`, when given, caps how
    many items this run authors by lowering the batch passed to run_drain's own `batch_size`
    (the same cap_categories() gate a launcher-tick batch is already bounded by) — no separate
    cap is invented here. Returns run_drain's report unchanged."""
    search_topic = source_topics.default_search_topic if search_topic is None else search_topic
    fetch_meta = drain.default_fetch_meta if fetch_meta is None else fetch_meta
    # Topic-search repos ARE already the canonical source (unlike launcher entries, which are often
    # forks of a better-known repo). Running drain's fork->canonical resolver here mis-fires on
    # generic name tokens — ppyne/lx_shell (10*, a real Cardputer shell) got "resolved" to
    # alebcay/awesome-shell, taking its wrong URL AND its thousands of stars to clear the floor.
    # So default to NO canonical redirect for topics; only redirect if a caller injects one.
    resolve_source = (lambda owner, repo: {}) if resolve_source is None else resolve_source

    report = drain.run_drain(
        fetch_catalog=lambda: source_topics.fetch_topic_repos(source_topics.DEFAULT_TOPICS, search=search_topic),
        batch_size=limit if limit is not None else BATCH_SIZE,
        max_per_category=MAX_PER_CATEGORY,
        fetch_meta=fetch_meta,
        ledger_path=ledger_path,
        today=today,
        resolve_source=resolve_source,
    )
    _print_report(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap how many items are authored this run (default: no limit — the full topic yield)")
    args = parser.parse_args()
    main(limit=args.limit)
