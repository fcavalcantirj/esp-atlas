"""EspAtlas Jr — GitHub-topics dry-run yield driver (jr/ingest_topics.py).

READ-ONLY report: of everything jr/source_topics.py's topic search surfaces, how much would the
launcher-drain's OWN admission gate (jr/drain.score_candidates -> jr/scorer.score_entry) actually
admit? This exists to size the GitHub-topics source before it is wired into anything — same
motivation as jr/ingest_awesome.py (the launcher pool is ~98% drained, DECISION-LOG.md), a
different discovery angle: GitHub's own topic tags instead of curated awesome-list markdown.

Never writes a firmware/recipe dir and never writes the ledger (jr/proposed_ledger.json is only
READ, via ledger.load_ledger) — safe to re-run at will while iterating on the source. NOT wired
into jr/tick.py's hourly run; that, and any real ledger recording of what this surfaces, is
follow-up work.

Reuses jr/drain.score_candidates (and, through it, jr/scorer.score_entry) for the judgment step —
the popularity floor and firmware-evidence rules are NOT re-implemented or loosened here. The
dedup-against-known-catalog/ledger split and the printed report are shared with any other
ingest_*.py driver via jr/ingest_common.py, not copy-pasted.

    python3 ingest_topics.py [--dry-run]   # --dry-run is accepted for clarity; every run is
                                            # read-only regardless of the flag
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
import tools  # noqa: E402
from ingest_common import dedup_known, print_report  # noqa: E402
from source_topics import DEFAULT_TOPICS, default_search_topic, fetch_topic_repos  # noqa: E402


def run_ingest(topics=DEFAULT_TOPICS, search_topic=default_search_topic, per_topic: int = 100,
              fetch_meta=drain.default_fetch_meta, ledger_path=ledger.DEFAULT_LEDGER_PATH,
              firmware_dir=None) -> dict:
    """The full dry-run, end to end. `search_topic` (jr/source_topics.py's topic-search client)
    and `fetch_meta` (jr/drain.py's GitHub-metadata fetcher — the SAME client a live drain run
    uses) are both injected so tests make no network call; `firmware_dir` likewise (default None
    — the real data/firmware, mirroring tools._catalogued_repos_and_tokens()'s own default) so a
    test can point at a tmp_path catalog instead of this clone's real, ever-growing one. Writes
    nothing: the ledger is loaded but never saved, and jr/drain.score_candidates never authors
    anything on its own — only jr/drain.author_selected (not called here) does."""
    candidates = fetch_topic_repos(topics, search=search_topic, per_topic=per_topic)
    catalogued_repos, catalogued_tokens = tools._catalogued_repos_and_tokens(firmware_dir=firmware_dir)
    ledger_state = ledger.load_ledger(ledger_path)
    unknown, known = dedup_known(candidates, catalogued_repos, ledger_state)
    scored, skipped = drain.score_candidates(unknown, catalogued_repos, catalogued_tokens, fetch_meta=fetch_meta)
    return {
        "total_candidates": len(candidates),
        "already_known": len(known),
        "would_admit": scored,
        "rejected": skipped,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                       help="accepted for clarity — every run of this script is read-only")
    parser.parse_args()
    print_report(run_ingest())
