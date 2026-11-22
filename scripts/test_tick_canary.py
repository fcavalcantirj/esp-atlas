"""scripts/tick_canary.py — a review-routed tick PR whose receipts hold merges itself, one a day."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import receipt_guard as rg
import tick_canary as tc

HEAD = "6c4e0607aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
BRANCH = "jr/tick-20261117-1900"


class FakeGh:
    def __init__(self, labels=("jr-review",), merged=(), queued=()):
        self.calls, self.labels, self.merged, self.queued = [], list(labels), list(merged), list(queued)

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps({"labels": [{"name": l} for l in self.labels]})
        if args[:2] == ("pr", "list"):
            assert "--label" in args and args[args.index("--label") + 1] == "jr-review"     # the cap counts review-routed merges only
            if args[args.index("--state") + 1] == "open":
                return json.dumps([{"headRefName": b, "autoMergeRequest": {"enabledAt": "x"}} for b in self.queued])
            return json.dumps([{"headRefName": b, "mergedAt": f"{d}T10:00:00Z"} for b, d in self.merged])
        return ""

    def merges(self):
        return [c for c in self.calls if c[:2] == ("pr", "merge")]


@pytest.fixture
def autonomy(tmp_path):
    def write(on=True):
        f = tmp_path / "autonomy.json"
        f.write_text(json.dumps({"tick_automerge": on, "demand_automerge": False}))
        return f
    return write


@pytest.fixture
def eligible(monkeypatch):
    def set_(problems=(), raise_=None):
        def check(repo, *, base, head, branch, **kw):
            if raise_:
                raise raise_
            return list(problems), ["E1/E2 data/recipes/x__y/recipe.md: receipt v3 PASS; live re-check v3 PASS — named"]
        monkeypatch.setattr(rg, "check", check)
    set_()
    return set_


def run(autonomy_path, gh, env=None, **kw):
    args = dict(pr=1803, head=HEAD, branch=BRANCH, base="origin/main", repo_slug="o/r", today="2026-11-17",
                env=env or {}, autonomy_path=autonomy_path, gh=gh)
    args.setdefault("paths", ["data/recipes/x__y/recipe.md"])
    args.update(kw)
    return tc.decide(**args)


def test_happy_path_requests_the_merge_at_the_exact_head(autonomy, eligible, capsys):
    gh = FakeGh()
    assert run(autonomy(True), gh) == "merge_requested"
    assert gh.merges() == [("pr", "merge", "1803", "--repo", "o/r", "--merge", "--auto", "--match-head-commit", HEAD)]
    assert "T5 eligible" in capsys.readouterr().out


def test_switches_off_mean_no_action(autonomy, eligible):
    gh = FakeGh()
    assert run(autonomy(False), gh) == "off" and gh.calls == []
    assert run(autonomy(True), gh, env={"JR_TICK_AUTOMERGE": "0"}) == "off" and gh.calls == []


def test_an_auto_routed_tick_pr_without_the_review_label_is_left_alone(autonomy, eligible):
    gh = FakeGh(labels=())
    assert run(autonomy(True), gh) == "not_review" and gh.merges() == []


def test_not_a_tick_branch(autonomy, eligible):
    gh = FakeGh()
    assert run(autonomy(True), gh, branch="jr/research-x") == "not_tick" and gh.calls == []


def test_at_most_four_review_routed_merges_per_day(autonomy, eligible):
    # 2026-11-21: Jr opened 10 review-routed tick PRs Nov 18-20 (about 3.3 a day) and one a day merged, so
    # the queue only grew and the tick re-proposed nothing its open PRs held (yield 0 over 24 ticks)
    assert tc.DAILY_CAP == 4
    three = [(f"jr/tick-20261117-{h}00", "2026-11-17") for h in (10, 11, 12)]
    gh = FakeGh(merged=three)
    assert run(autonomy(True), gh) == "merge_requested" and len(gh.merges()) == 1
    gh = FakeGh(merged=three + [("jr/tick-20261117-1300", "2026-11-17")])
    assert run(autonomy(True), gh) == "capped" and gh.merges() == []
    gh = FakeGh(merged=[(f"jr/tick-20261116-{h}00", "2026-11-16") for h in (10, 11, 12, 13, 14)])
    assert run(autonomy(True), gh) == "merge_requested"                 # yesterday's merges never count


def test_a_receipt_problem_or_an_unreadable_upstream_never_merges(autonomy, eligible, capsys):
    eligible(problems=["E2 data/recipes/x__y/recipe.md: receipt v3 PASS, but the live re-check is FAIL"])
    gh = FakeGh()
    assert run(autonomy(True), gh) == "not_eligible" and gh.merges() == []
    eligible(raise_=rg.Unreadable("HTTP 503"))
    gh = FakeGh()
    assert run(autonomy(True), gh) == "unreadable" and gh.merges() == []
    assert "re-checked on the next run" in capsys.readouterr().out


def test_dry_run_never_writes(autonomy, eligible):
    gh = FakeGh()
    assert run(autonomy(True), gh, dry_run=True) == "dry_run" and gh.merges() == []



# --- review BLOCK of #1809 (2026-11-19): a PR could switch its own canary on, or carry code the canary would merge

def test_a_pr_that_changes_anything_outside_its_scope_is_never_merged(autonomy, eligible):
    for paths in (["jr/autonomy.json"], ["data/recipes/x__y/recipe.md", "scripts/tick_canary.py"], [".github/workflows/validate.yml"]):
        gh = FakeGh()
        assert run(autonomy(True), gh, paths=paths) == "out_of_scope", paths
        assert not [c for c in gh.calls if c[:2] in (("pr", "merge"), ("pr", "ready"), ("pr", "edit"))]
    import demand_canary
    assert demand_canary.out_of_scope(None, demand_canary.DEMAND_SCOPE) is None          # unreadable: never merged


def test_the_switch_is_read_from_main_never_from_the_prs_tree(tmp_path):
    import subprocess as sp
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"]}
    g = lambda *a: sp.run(["git", *a], cwd=tmp_path, env=env, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "jr").mkdir()
    (tmp_path / "jr" / "autonomy.json").write_text('{"demand_automerge": false, "tick_automerge": false}')
    g("add", "."), g("commit", "-qm", "main")
    g("checkout", "-qb", "pr")
    (tmp_path / "jr" / "autonomy.json").write_text('{"demand_automerge": true, "tick_automerge": true}')
    g("commit", "-qam", "the PR turns itself on")
    import demand_canary
    p = demand_canary.trusted_autonomy("main", tmp_path)
    assert __import__("json").loads(p.read_text()) == {"demand_automerge": False, "tick_automerge": False}
    assert not demand_canary.trusted_autonomy("no-such-ref", tmp_path).exists()
