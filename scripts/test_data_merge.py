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


def test_the_workflow_installs_what_the_script_imports():
    """2026-11-23: every jr-data-merge run since #2007 failed with No module named 'yaml': the workflow ran the
    script without installing its imports. The workflow must install them before running it."""
    import yaml
    from pathlib import Path
    wf = yaml.safe_load((Path(__file__).resolve().parent.parent / ".github" / "workflows" / "jr-data-merge.yml").read_text())
    steps = wf["jobs"]["decide"]["steps"]
    run_at = next(i for i, s in enumerate(steps) if "scripts/data_merge.py" in str(s.get("run", "")))
    installs = " ".join(str(s.get("run", "")) for s in steps[:run_at])
    for need in ("pyyaml", "jsonschema", "-e apps/core"):
        assert need in installs, need


# --- backfill PRs (root-cause plan, 2026-11-26): own switch, board-only scope, re-derived, fields counted ------------

BF_ON = {"autonomy": {"backfill_automerge": True}, "env": {}}
BOARDS = [{"path": "data/boards/espressif/esp32-devkitc/board.md", "status": "modified"},
          {"path": "data/boards/espressif/esp32-s3-devkitc-1/board.md", "status": "modified"}]


def bf_pr(**over):
    return pr(headRefName="jr/tick-20261126-1300-bf", **over)


def bf_state(**over):
    s = {"checks": dict(GREEN), "behind_by": 0, "files": list(BOARDS), "bookkeeping_ok": True, "facts_today": 0,
         "backfill": {"boards": 2, "pass": 2, "fields": 5, "problems": []}, "fields_today": 0}
    s.update(over)
    return s


def test_a_backfill_pr_every_board_of_which_re_derives_merges():
    d = dm.decide(bf_pr(), bf_state(), switches=BF_ON, now=NOW)
    assert d["action"] == "merge", d


@pytest.mark.parametrize("over, sw, why", [
    ({}, ON, "backfill_automerge"),                                                    # its own switch
    ({"backfill": {"boards": 2, "pass": 1, "fields": 5, "problems": ["esp32-devkitc: FAIL"]}}, BF_ON, "re-deriv"),
    ({"backfill": {"boards": 0, "pass": 0, "fields": 0, "problems": []}}, BF_ON, "nothing"),   # zero claims: never
    ({"files": BOARDS + [{"path": "jr/proposed_ledger.json", "status": "modified"}]}, BF_ON, "scope"),
    ({"files": [{"path": "data/boards/x/y/board.md", "status": "added"}]}, BF_ON, "scope"),
    ({"backfill": {"boards": 2, "pass": 2, "fields": dm.MAX_FIELDS_PER_PR + 1, "problems": []}}, BF_ON, "per PR"),
    ({"fields_today": dm.MAX_FIELDS_PER_DAY}, BF_ON, "per day"),
])
def test_a_backfill_pr_outside_its_rules_never_merges(over, sw, why):
    d = dm.decide(bf_pr(), bf_state(**over), switches=sw, now=NOW)
    assert d["action"] != "merge" and why in d["why"], d


def test_a_build_target_switch_never_merges_a_backfill_and_vice_versa():
    assert dm.decide(pr(), state(), switches=BF_ON, now=NOW)["action"] != "merge"


def test_one_pr_whose_state_cannot_be_read_never_stops_the_run(monkeypatch, capsys):
    """Review BLOCK of #2126: a gather() failure on one PR (a missing dependency, a git error) used to kill the run."""
    import json as _json
    prs = [pr(number=5, headRefName="jr/tick-20261126-1300-bf"), pr(number=6)]
    monkeypatch.setattr(dm.demand_canary, "default_gh", lambda *a: _json.dumps(prs) if a[:2] == ("pr", "list") else "[]")
    def gather(gh, slug, p):
        if p["number"] == 5:
            raise AttributeError("module 'check_claims' has no attribute 'check_board_backfill'")
        return state()
    monkeypatch.setattr(dm, "gather", gather)
    assert dm.main([]) == 0
    out = capsys.readouterr().out
    assert "#5 skip: state unreadable" in out and "#6 " in out
