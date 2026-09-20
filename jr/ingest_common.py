"""EspAtlas Jr — shared dry-run yield-driver helpers (jr/ingest_common.py).

Factored out of the read-only "how much would the launcher-drain's admission gate actually
admit" drivers (jr/ingest_topics.py, and jr/ingest_awesome.py wherever/whenever it lands on this
tree) — the dedup-against-known-catalog/ledger split and the printed summary report are IDENTICAL
regardless of which source surfaced the candidates, so they live here once instead of being
copy-pasted per source. Neither function here makes a network call or writes anything.
"""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import ledger  # noqa: E402


def _owner_repo(github_url: str) -> str:
    fn = (github_url or "").strip().rstrip("/").replace("https://github.com/", "").lower()
    return "/".join(fn.split("/")[:2])


def dedup_known(candidates: list[dict], catalogued_repos: set[str],
               ledger_state: dict) -> tuple[list[dict], list[dict]]:
    """Split `candidates` into (unknown, already_known). "Already known" is a repo already
    catalogued (data/firmware, via tools._catalogued_repos_and_tokens) OR carrying ANY ledger
    record at all (proposed/rejected/seen/merged/expired) — a coarser bar than drain.prefilter's
    own BLOCKING_STATUSES check, deliberately: this is a read-only sizing report, so anything the
    ledger has ever recorded an opinion on is not worth re-surfacing here, not just the statuses
    that would block a real authoring run."""
    unknown, known = [], []
    for c in candidates:
        owner_repo = _owner_repo(c.get("github"))
        if not owner_repo or "/" not in owner_repo:
            known.append(c)
            continue
        if owner_repo in catalogued_repos or owner_repo.split("/")[0] in catalogued_repos:
            known.append(c)
            continue
        if ledger.lookup(ledger_state, repo=owner_repo) is not None:
            known.append(c)
            continue
        unknown.append(c)
    return unknown, known


def _reason_bucket(reason: str | None) -> str:
    return (reason or "unknown").split(":", 1)[0].strip()


def print_report(report: dict) -> None:
    """Print a per-candidate decision line, then a summary: total candidates, already-known,
    would-admit, and a per-reject-reason breakdown. Never writes anything — `report` is whatever
    a driver's `run_ingest()` returned."""
    for s in report["would_admit"]:
        rec = s["record"]
        print(f"{_owner_repo(rec['url'])} -> would-admit ({rec['id']})")
    for s in report["rejected"]:
        print(f"{_owner_repo(s.get('github'))} -> reject: {s.get('reason')}")

    buckets = Counter(_reason_bucket(s.get("reason")) for s in report["rejected"])
    print()
    print(f"total candidates: {report['total_candidates']}")
    print(f"already known: {report['already_known']}")
    print(f"would admit: {len(report['would_admit'])}")
    print("reject reasons:")
    for reason, count in buckets.most_common():
        print(f"  {reason}: {count}")
