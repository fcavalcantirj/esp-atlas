"""scripts/data_merge.py — the one serialized merger of Jr's data PRs (Jr redesign plan, step 6). Pure decisions over
fake PR states; no network, no git."""
import json

import pytest

import data_merge as dm

NOW = "2026-11-22T18:00:00Z"
ON = {"autonomy": {"build_target_automerge": True}, "env": {}}
GREEN = {c: "pass" for c in dm.REQUIRED_CHECKS}


def pr(**over):
    base = {"number": 7, "headRefName": "jr/tick-20261122-1700", "headRefOid": "a" * 40, "baseRefName": "main",
            "author": {"login": "espatlas-jr"}, "isCrossRepository": False, "labels": [{"name": "jr-data"}],
            "createdAt": "2026-11-22T17:01:00Z"}
    base.update(over)
    return base


def state(**over):
    s = {"checks": dict(GREEN), "behind_by": 0, "files": [
        {"path": "data/recipes/b__f/recipe.md", "status": "added"},
        {"path": "data/firmware/f/firmware.md", "status": "added"},
        {"path": "data/firmware/f/signals.json", "status": "added"},
        {"path": "jr/proposed_ledger.json", "status": "modified"},
        {"path": "docs/telemetry/yield.jsonl", "status": "modified"},
        {"path": "docs/telemetry/data-2026-11-22.md", "status": "added"}],
        "bookkeeping_ok": True, "facts_today": 0}
    s.update(over)
    return s


def decide(p=None, s=None, sw=ON, now=NOW):
    return dm.decide(p or pr(), s or state(), switches=sw, now=now)


def test_a_clean_data_pr_merges_at_its_exact_head():
    d = decide()
    assert d["action"] == "merge" and d["head"] == "a" * 40, d


@pytest.mark.parametrize("sw, why", [
    ({"autonomy": {}, "env": {}}, "build_target_automerge"),
    ({"autonomy": {"build_target_automerge": True}, "env": {"JR_TICK_AUTOMERGE": "0"}}, "JR_TICK_AUTOMERGE"),
])
def test_either_switch_off_means_no_merge(sw, why):
    d = decide(sw=sw)
    assert d["action"] == "skip" and why in d["why"]


@pytest.mark.parametrize("over, why", [
    (dict(author={"login": "someone"}), "author"),
    (dict(isCrossRepository=True), "fork"),
    (dict(baseRefName="dev"), "base"),
    (dict(headRefName="feat/x"), "branch"),
    (dict(labels=[]), "label"),
])
def test_only_jrs_own_labelled_tick_prs_are_eligible(over, why):
    d = decide(p=pr(**over))
    assert d["action"] == "skip" and why in d["why"], d


def test_pending_checks_wait_and_a_failed_check_never_merges():
    assert decide(s=state(checks={**GREEN, "claims": "pending"}))["action"] == "wait"
    d = decide(s=state(checks={**GREEN, "claims": "fail"}))
    assert d["action"] == "skip" and "claims" in d["why"]
    d = decide(s=state(checks={k: v for k, v in GREEN.items() if k != "quotes"}))
    assert d["action"] == "skip" and "quotes" in d["why"]                    # a missing required check never passes


def test_a_branch_behind_main_is_updated_never_merged():
    assert decide(s=state(behind_by=3))["action"] == "update-branch"


@pytest.mark.parametrize("files, why", [
    ([{"path": "data/recipes/b__f/recipe.md", "status": "modified"}], "existing record"),
    ([{"path": "data/recipes/b__f/recipe.md", "status": "removed"}], "existing record"),
    ([{"path": "data/boards/x/y/board.md", "status": "added"}], "scope"),
    ([{"path": "jr/tick.py", "status": "modified"}], "scope"),
    ([{"path": "data/firmware/g/signals.json", "status": "added"}], "signals"),     # no new firmware g in the PR
])
def test_anything_outside_the_data_scope_never_merges(files, why):
    d = decide(s=state(files=files))
    assert d["action"] == "skip" and why in d["why"], d


def test_bookkeeping_that_removes_entries_never_merges():
    d = decide(s=state(bookkeeping_ok=False))
    assert d["action"] == "skip" and "bookkeeping" in d["why"]


def test_the_fact_limits_hold():
    many = [{"path": f"data/recipes/b{i}__f/recipe.md", "status": "added"} for i in range(dm.MAX_FACTS_PER_PR + 1)]
    assert "per PR" in decide(s=state(files=many))["why"]
    assert "per day" in decide(s=state(facts_today=dm.MAX_FACTS_PER_DAY))["why"]


def test_a_stalled_pr_is_closed_as_a_timeout_not_a_rejection():
    d = decide(p=pr(createdAt="2026-11-22T10:00:00Z"), s=state(checks={**GREEN, "claims": "fail"}))
    assert d["action"] == "close-timeout"


def test_bookkeeping_transition_rule():
    base = {"by_id": {"a": {"status": "proposed"}}, "by_repo": {"o/r": {}}}
    assert dm.keys_kept(base, {"by_id": {"a": {"status": "expired"}, "b": {}}, "by_repo": {"o/r": {}}}, ("by_id", "by_repo"))
    assert not dm.keys_kept(base, {"by_id": {}, "by_repo": {"o/r": {}}}, ("by_id", "by_repo"))
    assert dm.lines_appended("x\ny\n", "x\ny\nz\n") and not dm.lines_appended("x\ny\n", "x\nz\n")


def test_quarantine_prs_have_their_own_scope_and_no_fact_limits():
    q = pr(headRefName="jr/quarantine-20261122", labels=[{"name": "jr-quarantine"}])
    ok = state(files=[{"path": "data/quarantine.json", "status": "modified"}], facts_today=999)
    assert decide(p=q, s=ok)["action"] == "merge"
    bad = state(files=[{"path": "data/quarantine.json", "status": "modified"}, {"path": "data/recipes/b__f/recipe.md", "status": "removed"}])
    assert decide(p=q, s=bad)["action"] == "skip"
