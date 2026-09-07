#!/usr/bin/env python3
"""Ledger guard — a tick PR may add memory, never rewrite history (scripts/ledger_guard.py).

Compares `jr/proposed_ledger.json` at HEAD with the base ref. Fails (exit 1, ::error::) when:
  - a record disappears (the ledger is append-only; expiry sets `expired`, it never deletes);
  - a `merged` record changes to anything but a PERMANENT rejection (a human veto: no `expires`);
  - a `proposed` record changes to anything but `merged` or a permanent rejection;
  - a `rejected` or `seen` record carries no `expires` unless it is a permanent rejection;
  - a record's `id` differs from its key, or the key is empty.
Only records the PR adds or changes are checked (legacy records are not re-litigated).
Tick #153 (2026-09-07) rewrote four merged records and one open proposal as 30-day rejections
and CI was green — this is the check that was missing. Offline: reads both refs with git show.

    python3 scripts/ledger_guard.py                    # base origin/$GITHUB_BASE_REF or origin/main
    python3 scripts/ledger_guard.py --base <ref>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEDGER = "jr/proposed_ledger.json"


def check(base: dict, head: dict) -> list[str]:
    """Pure: the violations between two ledgers ({'by_id': {...}} each)."""
    out: list[str] = []
    A, B = base.get("by_id") or {}, head.get("by_id") or {}
    for k in A:
        if k not in B:
            out.append(f"record removed: '{k}' (the ledger is append-only)")
    for k, rec in B.items():
        if k in A and A[k] == rec:
            continue                              # untouched by this PR: history is not re-litigated
        if not k or not isinstance(rec, dict):
            out.append(f"bad key {k!r}")
            continue
        if rec.get("id") != k:
            out.append(f"'{k}': id field {rec.get('id')!r} does not match its key")
        status = rec.get("status")
        permanent = status == "rejected" and not rec.get("expires")
        if status in ("rejected", "seen") and not rec.get("expires") and not permanent:
            out.append(f"'{k}': {status} without expires")
        old = A.get(k)
        if not old or old.get("status") == status:
            continue
        was = old.get("status")
        if was == "merged" and not permanent:
            out.append(f"'{k}': merged -> {status} (only a permanent rejection, a human veto, may change a merged record)")
        if was == "proposed" and not (status == "merged" or permanent):
            out.append(f"'{k}': proposed -> {status} (only merged or a permanent rejection may follow a proposal)")
    return out


def _show(ref: str, path: str, cwd: Path) -> dict:
    p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=cwd, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        return {"by_id": {}}
    return json.loads(p.stdout or "{}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=None)
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)
    base = args.base or (f"origin/{os.environ['GITHUB_BASE_REF']}" if os.environ.get("GITHUB_BASE_REF") else "origin/main")
    head_path = args.repo / LEDGER
    head = json.loads(head_path.read_text()) if head_path.exists() else {"by_id": {}}
    problems = check(_show(base, LEDGER, args.repo), head)
    for m in problems:
        print(f"::error file={LEDGER}::{m}")
    print(f"Ledger guard: {'green' if not problems else str(len(problems)) + ' problem(s)'} ({len(head.get('by_id') or {})} records vs {base})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
