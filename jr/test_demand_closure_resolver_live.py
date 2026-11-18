"""Autonomous RECONCILE closure of `resolver_live` work: after the delegate's CODE PR merges, the proof is the
hourly backfill writing the field on the vendor's boards. Fakes: `git show` answers per (ref, path)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import demand_closure
import research_work as rw

DAY = "2026-11-19"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
MERGE = "978cf97f" + "0" * 32
BOARDS = ["adafruit-feather-esp32-s3", "adafruit-qtpy-esp32-c3", "adafruit-metro-esp32-s3", "adafruit-huzzah32"]
PROV = {"vendor": "adafruit", "field": "download_mode", "missing": 20, "records": 26, "boards": BOARDS, "report_date": "2026-11-18"}


def record(board, with_field):
    extra = "download_mode:\n  mode: manual\n  steps: Hold BOOT, press RESET\n" if with_field else ""
    return f"---\nid: {board}\ntype: board\nbrand: adafruit\nname: {board}\nsoc: esp32-s3\n{extra}---\n\nBody.\n"


def candidate(expected=BOARDS):
    return {"term": rw.resolver_term(PROV), "source": rw.SOURCE_RESOLVER, "status": rw.STATUS_LINKED, "first_seen": "2026-11-18",
            "history": [], "linked_work": ["https://github.com/o/r/pull/12"], "resolver": dict(PROV),
            "validation": {"verified_on": DAY, "forbidden_ids": [], "verification_kind": rw.KIND_RESOLVER_LIVE,
                           "validated_by": "executor", "primary_sources": ["https://learn.adafruit.com/x"], "expected_ids": list(expected),
                           "identity_verified": True, "term_key": rw.term_key(rw.resolver_term(PROV))}}


def pr():
    return {"url": "https://github.com/o/r/pull/12", "state": "MERGED", "merged": True, "merge_sha": MERGE, "merged_at": f"{DAY}T10:00:00Z"}


def git_with(now_has: dict, merge_has: dict | None = None, unreadable=()):
    merge_has = merge_has or {}
    def git(*args):
        assert args[0] == "show"
        ref, path = args[1].split(":", 1)
        board = path.split("/")[3]
        if board in unreadable:
            return SimpleNamespace(returncode=128, stdout="", stderr="fatal: path does not exist")
        has = now_has.get(board, False) if ref == "HEAD" else merge_has.get(board, False)
        return SimpleNamespace(returncode=0, stdout=record(board, has), stderr="")
    return git


def test_three_expected_boards_gaining_the_field_after_the_merge_deliver():
    rec, why = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, now=NOW,
                                      git=git_with({b: True for b in BOARDS[:3]}))
    assert why == "" and rec["kind"] == rw.KIND_RESOLVER_LIVE and rec["verdict"] == "PASS"
    assert rec["gained"] == BOARDS[:3] and rec["vendor"] == "adafruit" and rec["field"] == "download_mode" and rec["merge_sha"] == MERGE
    assert rw._KIND_CHECKS[rw.KIND_RESOLVER_LIVE][0](rec, BOARDS, []) is None


def test_two_gained_is_pending_and_the_item_stays_live():
    rec, _ = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, now=NOW, git=git_with({b: True for b in BOARDS[:2]}))
    assert rec["verdict"] == "PENDING" and rw._KIND_CHECKS[rw.KIND_RESOLVER_LIVE][0](rec, BOARDS, []) is not None


def test_a_field_already_present_at_the_merge_was_not_gained_by_the_resolver():
    """The delegate must not write data/**; a board that carried the field at the merge is no evidence."""
    rec, _ = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, now=NOW,
                                    git=git_with({b: True for b in BOARDS}, merge_has={BOARDS[0]: True, BOARDS[1]: True}))
    assert rec["gained"] == BOARDS[2:] and rec["verdict"] == "PENDING"


def test_unreadable_boards_are_listed_and_fewer_expected_boards_need_all_of_them():
    rec, _ = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, now=NOW,
                                    git=git_with({b: True for b in BOARDS}, unreadable=(BOARDS[3],)))
    assert rec["unreadable"] == [BOARDS[3]] and rec["verdict"] == "PASS"
    rec, _ = demand_closure.observe(candidate(expected=BOARDS[:2]), pr(), {}, mined_revision=None, now=NOW,
                                    git=git_with({BOARDS[0]: True}))
    assert rec["verdict"] == "PENDING"
    rec, _ = demand_closure.observe(candidate(expected=BOARDS[:2]), pr(), {}, mined_revision=None, now=NOW,
                                    git=git_with({BOARDS[0]: True, BOARDS[1]: True}))
    assert rec["verdict"] == "PASS"


def test_no_merge_sha_or_unreadable_provenance_builds_no_receipt():
    rec, why = demand_closure.observe(candidate(), {**pr(), "merge_sha": ""}, {}, mined_revision=None, now=NOW, git=git_with({}))
    assert rec is None and "no merge sha" in why
    c = candidate(); c["resolver"]["field"] = "pinouts"
    rec, why = demand_closure.observe(c, pr(), {}, mined_revision=None, now=NOW, git=git_with({}))
    assert rec is None and "no readable resolver provenance" in why
