"""The tick counts and carries the yield rows its open tick PRs hold (stall:topics, 2026-11-19).

A tick that produced opens a jr-review PR, and its yield row waits there with the records it authored; main's
docs/telemetry/yield.jsonl only ever received the silent ticks, so the topics lane read 0/48u over 24 ticks
while #1828, #1875 and #1895 had authored 4 records, and a stall incident was raised against a working lane.
The rows are read at each PR's pinned head (yield_ledger.open_pr_rows), count in this tick's window, and ride
this tick's commit, like the decisions memory.carry_decisions carries.

Run: cd jr && python3 -m pytest test_tick_yield_carry.py -v
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta

import pending_prs
import publish
import tick
import yield_ledger as yl
from test_tick import JR_OWN, NOW, Proc, gh_ok, git_ok
from test_tick_dry_run import GROUNDABLE_MD, _checkout, _run, offline  # noqa: F401

LANES = ("backfill", "admit", "boardmap", "admit_topics")


def _rows(hours, topics=0):
    """One tick's rows `hours` before NOW: every lane silent except `topics` records authored."""
    return yl.rows_for_tick([{"name": n, "produced": topics if n == "admit_topics" else 0, "paths": [], "counts": {}}
                             for n in LANES], {"backfill": 3, "firmware": 3}, NOW - timedelta(hours=hours), units_topics=2)


def _review_pr(n, held_text):
    pr = {"number": n, "createdAt": (NOW - timedelta(hours=7)).isoformat().replace("+00:00", "Z"),
          "headRefName": f"jr/tick-x-{n}", "headRefOid": f"oid{n}", "mergeable": "MERGEABLE", "body": "",
          "files": [{"path": "data/firmware/xmas-tree/firmware.md"}, {"path": yl.RELPATH}], "changedFiles": 2,
          "labels": [{"name": "jr-review"}], **JR_OWN}
    read = ("api", "-H", pending_prs.RAW_MEDIA, f"repos/o/r/contents/{yl.RELPATH}?ref=oid{n}")
    return pr, read, held_text


def _gh(pr, read, text):
    base = gh_ok(prs=json.dumps([pr]))

    def gh(*a):
        if a == read:
            base.calls.append(a)
            return Proc(returncode=0, stdout=text)
        return base(*a)
    gh.calls = base.calls
    return gh


def test_a_producing_ticks_row_held_in_its_review_pr_counts_and_lands_on_main(tmp_path, monkeypatch, offline):  # noqa: F811
    seen = []

    def watcher(stall, yields, stages, rejects, now, dry_run):
        seen.append({"stall": stall, "yields": yields})
        return {"status": "ok", "incidents": [], "resolved": [], "nudges": []}
    checkout = _checkout(tmp_path / "checkout")
    silent = [r for h in range(24, 0, -1) if h != 7 for r in _rows(h)]          # main: every tick but 7h ago, all silent
    yl.append_rows(checkout / yl.RELPATH, silent)
    held = _rows(7, topics=1)                                                   # the tick 7h ago authored one record
    pr, read, text = _review_pr(1895, "".join(json.dumps(r, sort_keys=True) + "\n" for r in sorted(
        silent[:8] + held, key=lambda r: (r["tick"], r["stage"]))))
    monkeypatch.setattr(tick, "REPO", checkout)
    wt = tmp_path / "wt"
    shutil.copytree(checkout, wt)
    monkeypatch.setattr(publish.tempfile, "mkdtemp", lambda prefix="": str(wt))
    gh = _gh(pr, read, text)
    r = _run(False, git_ok(wt, diff=f"M\0{GROUNDABLE_MD}\0"), tmp_path, gh=gh, stall_watcher=watcher)
    assert not r.aborted, r.aborted
    assert gh.calls.count(read) == 1
    assert r.yields["topics"] == {"ticks": 24, "units": 48, "produced": 1}
    assert "topics" not in ((seen[0]["stall"] or {}).get("lanes") or [])
    on_disk = {(x["tick"], x["stage"]): x for x in yl.read_rows(wt / yl.RELPATH)}
    assert all(on_disk[(x["tick"], x["stage"])] == x for x in held)              # carried verbatim into this tick's commit
    assert yl.RELPATH in r.extra_paths
