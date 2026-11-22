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


# --- the quotes job (scripts/check_quotes.py, 2026-11-17): the verbatim check of a human review, in CI ---

QUOTES = "scripts/check_quotes.py"


def _quotes_step(jobs):
    steps = _steps_running(jobs["quotes"], QUOTES)
    assert len(steps) == 1, "the quotes job must run the quote check exactly once"
    return steps[0]


def test_the_quotes_job_runs_the_quote_check_on_pull_requests_only(jobs):
    assert _quotes_step(jobs)
    assert jobs["quotes"].get("if") == "github.event_name == 'pull_request'"


def test_nothing_swallows_the_quote_check_exit_code(jobs):
    step = _quotes_step(jobs)
    assert "continue-on-error" not in step and "continue-on-error" not in jobs["quotes"]
    assert not SHELL_OPERATORS.search(step["run"]), step["run"]


def test_the_quotes_job_installs_its_readers_before_the_check(jobs):
    """httpx fetches, PyYAML reads frontmatter, pypdf reads the cited datasheets (without it a PDF-only
    citation is inconclusive, never a verdict); esp_atlas_core is the frontmatter parser."""
    steps = jobs["quotes"]["steps"]
    at = next(i for i, s in enumerate(steps) if QUOTES in str(s.get("run", "")))
    runs = " ".join(str(s.get("run", "")) for s in steps[:at])
    for pkg in ("httpx", "pyyaml", "pypdf", "apps/core"):
        assert pkg in runs, pkg


def test_the_quotes_checkout_has_full_history_for_the_base_diff(jobs):
    checkout = next(s for s in jobs["quotes"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
# --- the demand-guard job (scripts/demand_guard.py, 2026-11-17): a demand PR changes only what it says ---

DEMAND_GUARD = "scripts/demand_guard.py"


def _demand_guard_step(jobs):
    steps = _steps_running(jobs["demand-guard"], DEMAND_GUARD)
    assert len(steps) == 1, "the demand-guard job must run the guard exactly once"
    return steps[0]


def test_the_demand_guard_runs_only_on_demand_pull_requests(jobs):
    assert _demand_guard_step(jobs)
    cond = jobs["demand-guard"].get("if", "")
    assert "github.event_name == 'pull_request'" in cond and "startsWith(github.head_ref, 'jr/research-')" in cond


def test_the_demand_guard_gets_the_pr_url_and_full_history_and_nothing_swallows_its_exit(jobs):
    step = _demand_guard_step(jobs)
    assert step.get("env", {}).get("PR_URL") == "${{ github.event.pull_request.html_url }}"
    assert "continue-on-error" not in step and "continue-on-error" not in jobs["demand-guard"]
    assert not SHELL_OPERATORS.search(step["run"]), step["run"]
    checkout = next(s for s in jobs["demand-guard"]["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout.get("with", {}).get("fetch-depth") == 0


# --- the demand-canary job (scripts/demand_canary.py, 2026-11-17): the merge click, as a job ----------

CANARY = "scripts/demand_canary.py"


def _canary_step(jobs):
    steps = _steps_running(jobs["demand-canary"], CANARY)
    assert len(steps) == 1
    return steps[0]


def test_the_canary_needs_every_machine_check_and_both_switches(jobs):
    job = jobs["demand-canary"]
    assert set(job["needs"]) >= {"schema", "tests", "jr-tests", "quotes", "demand-guard", "jr-pr-guard", "g2-guard", "ledger-guard"}
    cond = job["if"]
    assert "startsWith(github.head_ref, 'jr/research-')" in cond and "vars." not in cond   # the script enforces the kill
    assert job["permissions"] == {"contents": "write", "pull-requests": "write", "actions": "write"}


def test_the_canary_merges_at_the_exact_head_it_was_given(jobs):
    step = _canary_step(jobs)
    assert '--head "$PR_HEAD"' in step["run"] and step["env"]["PR_HEAD"] == "${{ github.event.pull_request.head.sha }}"
    assert '--pr "$PR_NUMBER"' in step["run"] and step["env"]["PR_NUMBER"] == "${{ github.event.pull_request.number }}"
    assert step["env"]["JR_DEMAND_AUTOMERGE"] == "${{ vars.JR_DEMAND_AUTOMERGE }}"
    assert "secrets.ESPATLAS_JR_TOKEN || github.token" in step["env"]["GH_TOKEN"]
    assert "continue-on-error" not in step and not SHELL_OPERATORS.search(step["run"]), step["run"]


def test_nothing_needs_the_canary(jobs):
    assert not any("demand-canary" in (j.get("needs") or []) for j in jobs.values())


# --- receipt-guard + tick-canary (2026-11-17): a review-routed tick PR merges on its receipts ----------

def test_the_receipt_guard_runs_on_tick_pull_requests_only_with_full_history(jobs):
    job = jobs["receipt-guard"]
    assert "startsWith(github.head_ref, 'jr/tick-')" in job["if"] and "github.event_name == 'pull_request'" in job["if"]
    step = next(s for s in job["steps"] if "scripts/receipt_guard.py" in str(s.get("run", "")))
    assert "continue-on-error" not in step and not SHELL_OPERATORS.search(step["run"])
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0


def test_the_tick_canary_needs_the_receipt_guard_and_every_machine_check_and_both_switches(jobs):
    job = jobs["tick-canary"]
    assert set(job["needs"]) >= {"schema", "tests", "jr-tests", "receipt-guard", "jr-pr-guard", "g2-guard", "ledger-guard"}
    assert "startsWith(github.head_ref, 'jr/tick-')" in job["if"] and "vars." not in job["if"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write", "actions": "write"}
    step = next(s for s in job["steps"] if "scripts/tick_canary.py" in str(s.get("run", "")))
    assert '--head "$PR_HEAD"' in step["run"] and step["env"]["PR_HEAD"] == "${{ github.event.pull_request.head.sha }}"
    assert step["env"]["JR_TICK_AUTOMERGE"] == "${{ vars.JR_TICK_AUTOMERGE }}"
    assert not any("tick-canary" in (j.get("needs") or []) for j in jobs.values())



# --- 3rd review of #1809 (2026-11-19): a canary decides with MAIN's code; the PR is only data in pr/ --------

def test_both_canaries_run_mains_code_against_the_pr_as_data(jobs):
    for name, script in (("demand-canary", "demand_canary.py"), ("tick-canary", "tick_canary.py")):
        checkouts = [s for s in jobs[name]["steps"] if "actions/checkout" in str(s.get("uses", ""))]
        trusted = [c for c in checkouts if (c.get("with") or {}).get("path") == "trusted"]
        pr = [c for c in checkouts if (c.get("with") or {}).get("path") == "pr"]
        # main's tip: base.sha is main at the PR's last head sync, a day old on older PRs (2026-11-19)
        assert trusted and trusted[0]["with"]["ref"] == "${{ github.event.repository.default_branch }}", name
        assert pr and len(checkouts) == 2, name
        assert all(c["with"].get("persist-credentials") is False for c in checkouts), name
        run = next(s["run"] for s in jobs[name]["steps"] if script in str(s.get("run", "")))
        assert run.startswith(f"python3 trusted/scripts/{script} --repo pr "), run



def test_the_receipt_guard_job_only_reports_it_never_turns_a_tick_pr_red(jobs):
    # 2026-11-19: "not eligible on receipts alone" exited 1 -> a red X and a failure email on every tick PR that
    # is simply waiting for a person (#1828, 3 red runs). The tick canary recomputes eligibility itself.
    step = next(s for s in jobs["receipt-guard"]["steps"] if "scripts/receipt_guard.py" in str(s.get("run", "")))
    assert "--report-only" in step["run"]
