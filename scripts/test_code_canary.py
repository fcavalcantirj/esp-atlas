"""scripts/code_canary.py — a code PR the agent reviewer PASSed at this exact head merges itself."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import code_canary as cc

HEAD = "5e9bb443b1aa89854c94f9d8338fd6204df522f6"
NOW = datetime(2026, 11, 17, 21, 0, tzinfo=timezone.utc)


def verdict(v="PASS", head=HEAD, findings=(), checked=("gh pr diff", "pytest jr/test_board_names.py")):
    return json.dumps({"verdict": v, "head": head, "findings": list(findings), "checked": list(checked)})


class FakeGh:
    def __init__(self, merged=()):
        self.calls, self.merged = [], list(merged)

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "list"):
            assert "--label" in args and args[args.index("--label") + 1] == cc.PASS_LABEL
            return json.dumps([{"number": n, "mergedAt": t} for n, t in self.merged])
        return ""

    def writes(self):
        return [c for c in self.calls if c[:2] in {("pr", "merge"), ("pr", "edit")}]


@pytest.fixture
def autonomy(tmp_path):
    def write(on=True):
        f = tmp_path / "autonomy.json"
        f.write_text(json.dumps({"code_automerge": on}))
        return f
    return write


def run(autonomy_path, gh, vj, env=None, **kw):
    args = dict(pr=1797, head=HEAD, verdict_json=vj, repo_slug="o/r", now=NOW, env=env or {}, autonomy_path=autonomy_path, gh=gh)
    args.update(kw)
    return cc.decide(**args)


def test_pass_at_the_exact_head_labels_and_requests_the_merge(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict()) == "merge_requested"
    assert gh.writes() == [("pr", "edit", "1797", "--repo", "o/r", "--add-label", cc.PASS_LABEL),
                           ("pr", "merge", "1797", "--repo", "o/r", "--merge", "--auto", "--match-head-commit", HEAD)]


def test_block_labels_needs_human_and_never_merges(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict("BLOCK", findings=[{"file": "x.py", "summary": "s", "failure": "f"}])) == "block"
    assert gh.writes() == [("pr", "edit", "1797", "--repo", "o/r", "--add-label", cc.HUMAN_LABEL)]


def test_a_verdict_for_another_head_is_no_verdict(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict(head="0000000")) == "stale_verdict" and gh.writes() == []


def test_switches_off_or_an_unreadable_verdict(autonomy):
    gh = FakeGh()
    assert run(autonomy(False), gh, verdict()) == "off" and gh.calls == []
    assert run(autonomy(True), gh, verdict(), env={"JR_CODE_AUTOMERGE": "0"}) == "off"
    with pytest.raises(cc.Unreadable):
        run(autonomy(True), gh, "not json")
    with pytest.raises(cc.Unreadable):
        run(autonomy(True), gh, json.dumps({"verdict": "MAYBE", "head": HEAD}))


def test_one_agent_merge_per_hour(autonomy):
    gh = FakeGh(merged=[(1790, "2026-11-17T20:30:00Z")])
    assert run(autonomy(True), gh, verdict()) == "capped" and gh.writes() == []
    gh = FakeGh(merged=[(1780, "2026-11-17T19:30:00Z")])          # older than an hour: does not count
    assert run(autonomy(True), gh, verdict()) == "merge_requested"


def test_dry_run_never_writes(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict(), dry_run=True) == "dry_run" and gh.writes() == []
    assert run(autonomy(True), gh, verdict("BLOCK"), dry_run=True) == "block" and gh.writes() == []
