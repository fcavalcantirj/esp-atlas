"""SPEC-jr-self-heal.md §5 — the stall_dispatch switch gates what the heal launcher may claim; the tick's
PR body carries the autonomy audit block (SPEC-espatlas-jr.md §3d rule 5)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import ci_watch as cw
import report
import tick
from test_ci_watch import NOW, incident
from test_ci_watch_stall import STAGES, STALL, Y

REPO = Path(__file__).resolve().parent.parent


def test_the_committed_switch_file_is_the_reviewed_autonomy_state():
    # owner, 2026-11-19: "make jr do the chores, site self sufficient" — on by reviewed PR. tick_automerge went on
    # the same day, once the evidence check stopped PASSing a sibling's recipe (rules v4, #1864): one
    # review-routed tick PR a day, every added recipe re-verified on the live upstream by receipt-guard
    doc = json.loads((REPO / "jr" / "autonomy.json").read_text())
    assert {k: v for k, v in doc.items() if not k.startswith("_")} == {
        "demand_automerge": True, "tick_automerge": True, "code_automerge": True, "stall_dispatch": True,
        "pr_fix_dispatch": True,
        # 2026-11-23, Jr redesign plan steps 8-9: build-target facts, both OFF through the 3-day shadow; each goes
        # on only by its own reviewed PR
        "build_target_shadow": False, "build_target_automerge": False}
    assert cw.stall_dispatch_allowed(REPO / "jr" / "autonomy.json", {}) is True
    assert cw.stall_dispatch_allowed(REPO / "jr" / "autonomy.json", {"JR_STALL_DISPATCH": "0"}) is False   # the kill

def test_stall_dispatch_needs_the_reviewed_flag_and_no_kill_variable(tmp_path):
    p = tmp_path / "autonomy.json"
    assert cw.stall_dispatch_allowed(p, {}) is False                                   # no file: off
    p.write_text(json.dumps({"stall_dispatch": True}))
    assert cw.stall_dispatch_allowed(p, {}) is True
    assert cw.stall_dispatch_allowed(p, {"JR_STALL_DISPATCH": "0"}) is False           # the instant kill
    assert cw.stall_dispatch_allowed(p, {"JR_STALL_DISPATCH": " 0 "}) is False
    p.write_text(json.dumps({"stall_dispatch": "true"}))
    assert cw.stall_dispatch_allowed(p, {}) is False                                   # a string is not true
    p.write_text("{broken")
    assert cw.stall_dispatch_allowed(p, {}) is False


def test_with_the_switch_off_claim_skips_stall_incidents_and_still_hands_out_ci_ones(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    cw.stall_watch(store, STALL, Y, NOW, stages=STAGES)
    assert store.claim(NOW, allow_stall=False) is None
    assert all(r["state"] == "open" for r in store._load()["incidents"].values())      # untouched, still open
    ci = store.record(incident(), NOW)
    got = store.claim(NOW, allow_stall=False)
    assert got["id"] == ci["id"] and got["state"] == "dispatched"
    got = store.claim("2026-11-13T00:30:00+00:00", allow_stall=True)
    assert got is not None and got["context"]["check"].startswith("stall:")


def test_the_cli_claim_consults_the_switch(tmp_path, monkeypatch, capsys):
    store_path = tmp_path / "incidents.json"
    cw.stall_watch(cw.Store(store_path), {**STALL, "lanes": ["backfill"]}, Y, NOW, stages=STAGES)
    monkeypatch.setattr(cw, "AUTONOMY_PATH", tmp_path / "autonomy.json")
    assert cw.main(["claim", "--state", str(store_path)]) == 3                          # off: nothing to claim
    (tmp_path / "autonomy.json").write_text(json.dumps({"stall_dispatch": True}))
    monkeypatch.setenv("JR_STALL_DISPATCH", "0")
    assert cw.main(["claim", "--state", str(store_path)]) == 3                          # killed
    monkeypatch.delenv("JR_STALL_DISPATCH")
    assert cw.main(["claim", "--state", str(store_path)]) == 0
    assert json.loads(capsys.readouterr().out)["context"]["check"] == "stall:backfill"


def test_the_pr_body_carries_the_autonomy_audit(tmp_path):
    r = report.TickReport(when=datetime(2026, 11, 18, 1, 0, tzinfo=timezone.utc))
    r.split = {"backfill": 1, "firmware": 5}
    r.yields = Y
    r.stall_watch = {"status": "ok", "incidents": ["abc", "stall:topics already open"], "resolved": ["def"], "nudges": []}
    r.work_audit = {"pam": {"delivered": 3, "abandoned": 1, "reserved": 1}, "search": {"delivered": 1, "abandoned": 2}}
    body = report.render_pr_body(r)
    assert "### Autonomy audit" in body
    assert "- split: backfill 1 / firmware 5 unit(s) · yield backfill 0/72u firmware 0/72u topics 0/48u over 24 tick(s)" in body
    assert "- stall incidents: recorded 1, already open 1, resolved 1" in body
    assert "- demand work (receipts on main): pam: abandoned 1, delivered 3, reserved 1 · search: abandoned 2, delivered 1" in body
    assert body.index("### Autonomy audit") < body.index("<details><summary>Stage log</summary>")
    quiet = report.TickReport(when=r.when)
    assert "Autonomy audit" not in report.render_pr_body(quiet)                       # a manual --track run has no split


def test_work_audit_counts_receipts_by_class_and_state(tmp_path):
    p = tmp_path / "work-receipts.json"
    assert tick.work_audit(p) == {}
    p.write_text(json.dumps({"version": 1, "receipts": [
        {"key": "a", "source": "pam_feed", "state": "delivered"}, {"key": "b", "source": "pam_feed", "state": "reserved"},
        {"key": "c", "source": "gsc_query", "state": "abandoned"}, {"key": "d", "source": "ga4 search_empty", "state": "delivered"},
        "junk"]}))
    # classes come from research_work.class_of: the hygiene and resolver classes count under their own
    # names once their PRs land; on this branch every non-PAM source is search
    assert tick.work_audit(p) == {"pam": {"delivered": 1, "reserved": 1}, "search": {"abandoned": 1, "delivered": 1}}
