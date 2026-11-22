"""Tests for scripts/validate_main.py: main's head always gets a validate run.

2026-11-19: the first PR the machine merged (#1799, merge commit 9ba8d76f, by the workflow token) had NO
workflow run on main. GitHub starts no workflow for a push made with GITHUB_TOKEN; the documented exception is
workflow_dispatch. The CI watcher reads the newest validate run on main, so an unchecked merge was invisible.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import validate_main as vm

REPO = Path(__file__).resolve().parent.parent
VALIDATE = REPO / ".github" / "workflows" / "validate.yml"
AGENT_REVIEW = REPO / ".github" / "workflows" / "agent-review.yml"
HEAD = "9ba8d76fb66fb4807bd825d0c1428954820676ff"


class Gh:
    def __init__(self, runs, head=HEAD, fail=()):
        self.runs, self.head, self.fail, self.calls = runs, head, fail, []

    def __call__(self, *args):
        self.calls.append(args)
        if any(f in " ".join(args) for f in self.fail):
            raise RuntimeError("gh: HTTP 403")
        if args[:2] == ("api", "repos/o/r/commits/main"):
            return json.dumps({"sha": self.head})
        if args[0] == "api" and "/actions/workflows/validate.yml/runs" in args[1]:
            assert f"head_sha={self.head}" in args[1]
            return json.dumps({"total_count": len(self.runs), "workflow_runs": self.runs})
        if args[:2] == ("workflow", "run"):
            return ""
        raise AssertionError(args)

    @property
    def dispatches(self):
        return [c for c in self.calls if c[:2] == ("workflow", "run")]


def test_a_head_without_a_validate_run_gets_one_dispatched_on_main():
    gh = Gh(runs=[])
    assert vm.ensure(gh, "o/r") == "dispatched"
    assert gh.dispatches == [("workflow", "run", "validate.yml", "--repo", "o/r", "--ref", "main")]


@pytest.mark.parametrize("status", ["queued", "in_progress", "completed"])
def test_a_head_that_already_has_a_run_in_any_state_is_left_alone(status):
    gh = Gh(runs=[{"id": 1, "status": status, "head_sha": HEAD}])
    assert vm.ensure(gh, "o/r") == "has_run"
    assert gh.dispatches == []


def test_a_dry_run_dispatches_nothing():
    gh = Gh(runs=[])
    assert vm.ensure(gh, "o/r", dry_run=True) == "would_dispatch"
    assert gh.dispatches == []


@pytest.mark.parametrize("broken", ["commits/main", "validate.yml/runs", "workflow run"])
def test_github_trouble_is_reported_and_never_fails_the_canary_job(broken, capsys):
    gh = Gh(runs=[], fail=(broken,))
    assert vm.main(["--repo-slug", "o/r"], gh=gh) == 0
    assert "unavailable" in capsys.readouterr().out


def test_an_unreadable_run_list_never_dispatches():
    gh = Gh(runs=[], fail=("validate.yml/runs",))
    assert vm.ensure(gh, "o/r").startswith("unavailable")
    assert gh.dispatches == []


@pytest.mark.parametrize("doc", [{"message": "Not Found"}, {"workflow_runs": None}, [], "x"])
def test_an_answer_that_is_not_a_run_list_never_dispatches(doc):
    class Odd(Gh):
        def __call__(self, *args):
            if args[0] == "api" and "/actions/workflows/" in args[1]:
                self.calls.append(args)
                return json.dumps(doc)
            return super().__call__(*args)
    gh = Odd(runs=[])
    assert vm.ensure(gh, "o/r").startswith("unavailable")
    assert gh.dispatches == []


# --- the workflows ---------------------------------------------------------------------------------------

def _wf(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(wf):
    return wf.get("on", wf.get(True))            # PyYAML reads a bare `on:` key as True


def test_validate_can_be_started_by_hand_or_by_a_workflow_token():
    assert "workflow_dispatch" in _on(_wf(VALIDATE))


@pytest.mark.parametrize("path,job,script", [(AGENT_REVIEW, "code-canary", "scripts/validate_main.py"),
                                             (VALIDATE, "demand-canary", "trusted/scripts/validate_main.py"),
                                             (VALIDATE, "tick-canary", "trusted/scripts/validate_main.py")])
def test_every_canary_ends_by_making_sure_main_has_its_ci(path, job, script):
    j = _wf(path)["jobs"][job]
    last = j["steps"][-1]
    run = last["run"].strip()
    if script.startswith("trusted/"):                     # main's copy; a PR whose base predates it says so, loudly
        assert run == (f'if [ -f {script} ]; then python3 {script}; else echo "validate-main: this PR\'s base '
                       'predates the script; skipped"; fi')
    else:
        assert run == f"python3 {script}"
    assert last["if"] == "always()"                       # also when the canary step refused or crashed
    assert last["env"]["GH_TOKEN"] == "${{ github.token }}"   # the workflow token may dispatch; a PAT is not needed
    assert j["permissions"]["actions"] == "write"
    assert not last.get("continue-on-error")              # the script itself never fails; nothing hides a crash


def test_no_job_but_the_three_canaries_may_write_actions():
    for path in (VALIDATE, AGENT_REVIEW):
        wf = _wf(path)
        assert "actions" not in (wf.get("permissions") or {})
        for name, j in wf["jobs"].items():
            if (j.get("permissions") or {}).get("actions") == "write":
                assert name in ("code-canary", "demand-canary", "tick-canary"), name


def test_the_jobs_that_only_make_sense_on_a_pull_request_stay_off_a_dispatched_run():
    jobs = _wf(VALIDATE)["jobs"]
    for name in ("quotes", "demand-guard", "demand-canary", "receipt-guard", "tick-canary"):
        assert "github.event_name == 'pull_request'" in jobs[name]["if"], name
