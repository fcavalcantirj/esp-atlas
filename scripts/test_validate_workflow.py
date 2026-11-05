"""Tests for .github/workflows/validate.yml: the new-link check rides the REQUIRED schema check.

`schema` is a required status check in branch protection; a separate job is not. So the
new-link check is a pull_request-only step of `schema` itself: a confirmed-dead link added by a
PR turns `schema` red and blocks merge, with no branch-protection change. These tests pin the
shape that makes that true: the step exists, nothing swallows its exit code, the checkout has
the history the base diff needs, and no second job runs the same network check.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "validate.yml"
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


def test_the_schema_checkout_has_full_history_for_the_base_diff(jobs):
    checkout = next(s for s in jobs["schema"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 0


def test_no_separate_new_links_job_runs_the_check_twice(jobs):
    assert "new-links" not in jobs
    assert [name for name, job in jobs.items() if _steps_running(job, SCRIPT)] == ["schema"]
