"""Tests for .github/workflows/validate.yml: the gates that matter ride REQUIRED status checks.

`schema` and `tests` are required checks in branch protection; a separate job is not, and a
continue-on-error step never blocks anything.

* The new-link check is a pull_request-only step of `schema` itself: a confirmed-dead link added
  by a PR turns `schema` red and blocks merge, with no branch-protection change. These tests pin
  the shape that makes that true: the step exists, nothing swallows its exit code, the checkout
  has the history the base diff needs, and no second job runs the same network check.
* The web unit tests (apps/web lib/*.test.ts, public-copy guard included) run inside the
  `tests` job — not in a side job branch protection does not know about, and never as
  continue-on-error.
"""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "validate.yml"
WEB = REPO / "apps" / "web"
SCRIPT = "scripts/new_link_check.py"
SHELL_OPERATORS = re.compile(r"[|;&]|\bset\s+\+e\b")


@pytest.fixture(scope="module")
def jobs():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _steps_running(job, script):
    return [s for s in job.get("steps", []) if script in str(s.get("run", ""))]


def _new_link_step(jobs):
    steps = _steps_running(jobs["schema"], SCRIPT)
    assert len(steps) == 1, "the schema job must run the new-link check exactly once"
    return steps[0]


def test_the_schema_job_runs_the_new_link_check(jobs):
    assert _new_link_step(jobs)


def test_the_new_link_step_only_runs_on_pull_requests(jobs):
    assert _new_link_step(jobs).get("if") == "github.event_name == 'pull_request'"


def test_nothing_swallows_the_new_link_exit_code(jobs):
    step = _new_link_step(jobs)
    assert "continue-on-error" not in step
    assert "continue-on-error" not in jobs["schema"]
    assert "shell" not in step
    assert not SHELL_OPERATORS.search(step["run"]), step["run"]


def test_pyyaml_is_installed_before_the_new_link_check(jobs):
    """Without PyYAML every YAML URL is inconclusive: the check would pass blind."""
    steps = jobs["schema"]["steps"]
    installs = [i for i, s in enumerate(steps) if "pip install" in str(s.get("run", "")) and "pyyaml" in s["run"]]
    assert installs and installs[0] < steps.index(_new_link_step(jobs))


def test_the_schema_checkout_has_full_history_for_the_base_diff(jobs):
    checkout = next(s for s in jobs["schema"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 0


def test_no_separate_new_links_job_runs_the_check_twice(jobs):
    assert "new-links" not in jobs
    assert [name for name, job in jobs.items() if _steps_running(job, SCRIPT)] == ["schema"]


def _tests_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["tests"]


def _web_step(steps: list[dict], run: str) -> dict:
    matches = [s for s in steps if s.get("run") == run and s.get("working-directory") == "apps/web"]
    assert len(matches) == 1, f"expected exactly one `{run}` step in apps/web, got {matches}"
    return matches[0]


def test_tests_job_sets_up_node_22_then_installs_and_runs_the_web_suite():
    job = _tests_job()
    steps = job["steps"]
    assert "continue-on-error" not in job

    node = [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-node@")]
    assert len(node) == 1, "the tests job needs exactly one actions/setup-node step"
    assert str(steps[node[0]]["with"]["node-version"]) == "22"

    ci, test = _web_step(steps, "npm ci"), _web_step(steps, "npm test")
    assert node[0] < steps.index(ci) < steps.index(test)
    for step in (steps[node[0]], ci, test):
        assert "continue-on-error" not in step, f"{step} must block the job"


def test_web_suite_is_not_a_separate_job():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    others = [name for name, job in jobs.items() if name != "tests" and "npm test" in json.dumps(job)]
    assert others == []


def test_npm_test_runs_the_public_copy_guard():
    script = json.loads((WEB / "package.json").read_text())["scripts"]["test"]
    argv = shlex.split(script)
    assert argv[:2] == ["node", "--test"]
    ran = {p.relative_to(WEB).as_posix() for pattern in argv[2:] for p in WEB.glob(pattern)}
    assert "lib/public-copy.test.ts" in ran
