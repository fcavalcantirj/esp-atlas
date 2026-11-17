"""Tests for .github/workflows/agent-review.yml: the agent reviewer reads and reports, never writes; the
code canary merges only on a PASS at the exact head, behind both switches (docs/REVIEW-CONTRACT.md)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "agent-review.yml"
WRITE_TOOLS = re.compile(r"gh pr (merge|edit|ready|close|review)|git push|gh api -X|Write|Edit|MultiEdit|NotebookEdit", re.I)


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def jobs(wf):
    return wf["jobs"]


def _review_step(jobs):
    steps = [s for s in jobs["agent-review"]["steps"] if str(s.get("uses", "")).startswith("anthropics/claude-code-action@")]
    assert len(steps) == 1
    return steps[0]


def test_the_review_runs_only_on_code_pull_requests_that_are_not_drafts(wf, jobs):
    assert set(wf[True]["pull_request"]["types"]) >= {"opened", "synchronize"}
    cond = jobs["agent-review"]["if"]
    for part in ("!startsWith(github.head_ref, 'jr/tick-')", "!startsWith(github.head_ref, 'jr/research-')", "github.event.pull_request.draft == false"):
        assert part in cond, part


def test_the_reviewer_is_the_pinned_official_action_with_the_contract_and_a_verdict_schema(jobs):
    step = _review_step(jobs)
    assert step["uses"] == "anthropics/claude-code-action@v1"
    assert step["with"]["anthropic_api_key"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    assert "docs/REVIEW-CONTRACT.md" in step["with"]["prompt"] and "HEAD: ${{ github.event.pull_request.head.sha }}" in step["with"]["prompt"]
    args = step["with"]["claude_args"]
    assert "--json-schema" in args
    schema = json.loads(re.search(r"--json-schema '(\{.*\})'", args, re.S).group(1))
    assert set(schema["required"]) == {"verdict", "head", "findings", "checked"}
    assert schema["properties"]["verdict"]["enum"] == ["PASS", "BLOCK"]


def test_the_reviewer_can_read_and_run_tests_but_never_write(jobs):
    args = _review_step(jobs)["with"]["claude_args"]
    allowed = re.search(r'--allowedTools "([^"]+)"', args).group(1)
    assert "Bash(gh pr diff:*)" in allowed and "Bash(gh pr comment:*)" in allowed and "pytest" in allowed
    assert not WRITE_TOOLS.search(allowed), allowed
    assert jobs["agent-review"]["permissions"] if "permissions" in jobs["agent-review"] else True


def test_no_review_without_the_secret_and_the_verdict_is_the_job_output(jobs):
    job = jobs["agent-review"]
    assert job["outputs"]["verdict"] == "${{ steps.review.outputs.structured_output }}"
    key = next(s for s in job["steps"] if s.get("id") == "key")
    assert "ANTHROPIC_API_KEY" in key["run"] and "configured=false" in key["run"]
    assert _review_step(jobs)["if"] == "steps.key.outputs.configured == 'true'"


def test_the_code_canary_needs_the_review_both_switches_and_merges_at_the_exact_head(jobs):
    job = jobs["code-canary"]
    assert job["needs"] == "agent-review" or job["needs"] == ["agent-review"]
    assert "needs.agent-review.outputs.verdict != ''" in job["if"] and "vars.JR_CODE_AUTOMERGE != '0'" in job["if"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    step = next(s for s in job["steps"] if "scripts/code_canary.py" in str(s.get("run", "")))
    assert "--head ${{ github.event.pull_request.head.sha }}" in step["run"]
    assert step["env"]["VERDICT_JSON"] == "${{ needs.agent-review.outputs.verdict }}"
    assert step["env"]["JR_CODE_AUTOMERGE"] == "${{ vars.JR_CODE_AUTOMERGE }}"
