"""memory.carry_decisions: a tick carries the TTL'd decisions an open tick PR committed (held for the
owner's review, or about to be closed as superseded) into its own ledger, so one review question never
holds a tick's admit progress off main. Same refusals as memory._write; ledger_guard passes by construction."""
from __future__ import annotations

import copy
import importlib.util
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import memory

NOW = datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc)
_spec = importlib.util.spec_from_file_location(
    "ledger_guard", Path(__file__).resolve().parent.parent / "scripts" / "ledger_guard.py")
ledger_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger_guard)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def rec(fid, status="rejected", repo=None, hours_ago=1, ttl_days=30, **extra):
    r = {"id": fid, "repo": repo or f"o/{fid}", "status": status, "timestamp": iso(NOW - timedelta(hours=hours_ago)),
         "pr_ref": None}
    if ttl_days is not None and status in ("rejected", "seen"):
        r["expires"] = iso(NOW - timedelta(hours=hours_ago) + timedelta(days=ttl_days))
    if status == "rejected":
        r.setdefault("reason", "below_floor: 3 stars")
    r.update(extra)
    return r


def write(path, *records):
    doc = {"by_id": {r["id"]: r for r in records}, "by_repo": {r["repo"]: r["id"] for r in records}}
    path.write_text(json.dumps(doc, indent=2) + "\n")
    return path


def src(*records, pr="#9"):
    return (pr, {r["id"]: r for r in records})


def by_id(path):
    return memory.load(path)["by_id"]


def test_carries_a_ttl_rejection_and_a_seen_note_main_lacks(tmp_path):
    lp = write(tmp_path / "l.json")
    a, b = rec("a"), rec("b", status="seen")
    got = memory.carry_decisions([src(a, b, pr="#1703")], path=lp, now=NOW)
    assert got == [("#1703", "a"), ("#1703", "b")]
    led = memory.load(lp)
    assert led["by_id"]["a"] == a and led["by_id"]["b"] == b          # verbatim: timestamp, expires, reason
    assert led["by_repo"]["o/a"] == "a"


def test_never_writes_over_merged_proposed_or_a_permanent_rejection(tmp_path):
    lp = write(tmp_path / "l.json", rec("m", status="merged", hours_ago=50),
               rec("p", status="proposed", hours_ago=50), rec("v", ttl_days=None, hours_ago=50))
    before = by_id(lp)
    got = memory.carry_decisions([src(rec("m"), rec("p"), rec("v"))], path=lp, now=NOW)
    assert got == [] and by_id(lp) == before


def test_the_newer_decision_wins(tmp_path):
    ours_new, ours_old = rec("n", hours_ago=1, reason="ours"), rec("o", hours_ago=9, reason="ours")
    lp = write(tmp_path / "l.json", ours_new, ours_old, rec("x", status="expired", hours_ago=900))
    got = memory.carry_decisions([src(rec("n", hours_ago=5), rec("o", hours_ago=2, reason="theirs"),
                                      rec("x", hours_ago=2, reason="theirs"))], path=lp, now=NOW)
    led = by_id(lp)
    assert led["n"]["reason"] == "ours"
    assert led["o"]["reason"] == "theirs" and led["x"]["reason"] == "theirs"
    assert sorted(f for _, f in got) == ["o", "x"]


def test_skips_what_another_step_owns_or_that_is_not_a_live_ttl_decision(tmp_path):
    lp = write(tmp_path / "l.json")
    records = [rec("exp", hours_ago=24 * 40),                         # expired at now
               rec("prop", status="proposed"),                       # hydrate_open_pr_ledger owns proposals
               rec("merged", status="merged"),
               rec("perm", ttl_days=None),                           # only a closed PR or a human vetoes
               rec("rev", review={"outcome": "raised"}),             # review_memory owns review decisions
               rec("noexp", status="seen", ttl_days=None),           # a seen note without expires is corrupt
               {**rec("mismatch"), "id": "other"}]
    src_led = {r["id"] if r["id"] != "other" else "mismatch": r for r in records}
    src_led[""] = rec("blank")
    src_led["notadict"] = "x"
    assert memory.carry_decisions([("#9", src_led)], path=lp, now=NOW) == []
    assert by_id(lp) == {}


def test_a_repo_id_a_protected_record_owns_is_never_shadowed(tmp_path):
    lp = write(tmp_path / "l.json", rec("old-name", status="merged", repo="o/old", repo_id=42, hours_ago=90))
    got = memory.carry_decisions([src(rec("new-name", repo="o/new", repo_id=42))], path=lp, now=NOW)
    assert got == [] and "new-name" not in by_id(lp)


def test_by_repo_never_moves_off_a_protected_record(tmp_path):
    lp = write(tmp_path / "l.json", rec("fw", status="merged", repo="o/fw", hours_ago=90))
    got = memory.carry_decisions([src(rec("repo-note:o/fw", repo="o/fw"))], path=lp, now=NOW)
    led = memory.load(lp)
    assert got == [("#9", "repo-note:o/fw")] and led["by_repo"]["o/fw"] == "fw"


def test_later_sources_win_over_earlier_ones(tmp_path):
    lp = write(tmp_path / "l.json")
    memory.carry_decisions([src(rec("a", hours_ago=5, reason="older"), pr="#1701"),
                            src(rec("a", hours_ago=2, reason="newer"), pr="#1703")], path=lp, now=NOW)
    assert by_id(lp)["a"]["reason"] == "newer"


def test_nothing_carried_writes_nothing(tmp_path):
    lp = write(tmp_path / "l.json", rec("a"))
    mtime = lp.stat().st_mtime_ns
    text = lp.read_text()
    assert memory.carry_decisions([src(rec("a"))], path=lp, now=NOW) == []
    assert lp.read_text() == text and lp.stat().st_mtime_ns == mtime


def _random_record(rng, fid):
    status = rng.choice(["rejected", "seen", "merged", "proposed", "expired"])
    ttl = rng.choice([None, 7, 30]) if status == "rejected" else (rng.choice([7, 30]) if status == "seen" else None)
    extra = {"repo_id": rng.choice([1, 2, 3])} if rng.random() < 0.3 else {}
    if rng.random() < 0.1:
        extra["review"] = {"outcome": "raised"}
    return rec(fid, status=status, repo=f"o/{rng.choice('abcdef')}", hours_ago=rng.randint(1, 24 * 40),
               ttl_days=ttl, **extra)


def test_property_guard_clean_and_idempotent(tmp_path):
    rng = random.Random(1702)
    for trial in range(300):
        ids = [f"f{i}" for i in range(8)]
        base = [_random_record(rng, f) for f in ids if rng.random() < 0.6]
        lp = write(tmp_path / f"l{trial}.json", *base)
        before = copy.deepcopy(json.loads(lp.read_text()))
        sources = [(f"#{n}", {f: _random_record(rng, f) for f in ids if rng.random() < 0.6}) for n in range(3)]
        memory.carry_decisions(sources, path=lp, now=NOW)
        after = json.loads(lp.read_text())
        assert ledger_guard.check(before, after) == [], (trial, ledger_guard.check(before, after))
        assert memory.carry_decisions(sources, path=lp, now=NOW) == []        # idempotent


# --- what our older record knew is kept, like memory._write keeps it (#1705 review, DasBrow) ------

def test_a_carry_keeps_our_older_records_history_and_aliases(tmp_path):
    old = {"id": "prev", "status": "rejected", "reason": "first look", "timestamp": iso(NOW - timedelta(days=40))}
    ours = rec("a", hours_ago=9, reason="ours", history=[old], aliases=["o/a-old"])
    lp = write(tmp_path / "l.json", ours)
    theirs = rec("a", hours_ago=2, reason="theirs", aliases=["o/a-new"])
    assert memory.carry_decisions([src(theirs)], path=lp, now=NOW) == [("#9", "a")]
    got = by_id(lp)["a"]
    assert got["reason"] == "theirs"
    assert got["history"][0] == old                                   # ours' own history, first
    assert got["history"][1] == {k: v for k, v in ours.items() if k != "history"}   # then ours itself
    assert set(got["aliases"]) == {"o/a-old", "o/a-new"}


def test_a_carry_never_duplicates_history_the_pr_already_has(tmp_path):
    old = {"id": "prev", "status": "rejected", "reason": "first look", "timestamp": iso(NOW - timedelta(days=40))}
    ours = rec("a", hours_ago=9, reason="ours", history=[old])
    lp = write(tmp_path / "l.json", ours)
    snapshot = {k: v for k, v in ours.items() if k != "history"}
    theirs = rec("a", hours_ago=2, reason="theirs", history=[old, snapshot])   # the PR's _write already kept them
    memory.carry_decisions([src(theirs)], path=lp, now=NOW)
    assert by_id(lp)["a"]["history"] == [old, snapshot]


def test_a_plain_older_record_adds_no_history(tmp_path):
    lp = write(tmp_path / "l.json", rec("a", hours_ago=9, reason="ours"))
    memory.carry_decisions([src(rec("a", hours_ago=2, reason="theirs"))], path=lp, now=NOW)
    assert "history" not in by_id(lp)["a"]                            # _write adds history only past a review/history


def test_a_live_owner_review_decision_on_main_is_never_replaced(tmp_path):
    ours = rec("a", hours_ago=9, reason="needs_review_target: …", review={"outcome": "open", "pr_ref": "#1703"})
    lp = write(tmp_path / "l.json", ours)
    assert memory.carry_decisions([src(rec("a", hours_ago=2, reason="theirs"))], path=lp, now=NOW) == []
    assert by_id(lp)["a"] == ours


def test_a_lapsed_review_decision_may_be_replaced_and_is_kept_in_history(tmp_path):
    ours = {**rec("a", hours_ago=24 * 70, ttl_days=60, review={"outcome": "closed"}), "status": "expired"}
    lp = write(tmp_path / "l.json", ours)
    assert memory.carry_decisions([src(rec("a", hours_ago=2, reason="theirs"))], path=lp, now=NOW) == [("#9", "a")]
    assert by_id(lp)["a"]["history"][-1] == ours
