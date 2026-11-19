"""Tests for .github/workflows/agent-review.yml: the API lane runs only on the runner's `review-fallback`
label, reads and reports, never writes; the code canary runs on every marker comment and merges only on a
PASS at the PR's current head, behind both switches (docs/REVIEW-CONTRACT.md, "Who runs it")."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "agent-review.yml"
WRITE_TOOLS = re.compile(r"gh pr (merge|edit|ready|close|review|comment)|git push|gh api -X|Write|Edit|MultiEdit|NotebookEdit", re.I)


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


def test_the_api_lane_runs_only_when_the_runner_labelled_the_pr_review_fallback(wf, jobs):
    assert wf[True]["pull_request"]["types"] == ["labeled"]          # never a push: the subscription lane owns those
    cond = jobs["agent-review"]["if"]
    assert "github.event.label.name == 'review-fallback'" in cond
    for part in ("!startsWith(github.head_ref, 'jr/tick-')", "!startsWith(github.head_ref, 'jr/research-')",
                 "!startsWith(github.head_ref, 'jr/heal-')", "github.event.pull_request.draft == false"):
        assert part in cond, part


def test_the_reviewer_is_the_pinned_official_action_with_the_contract_and_a_verdict_schema(jobs):
    step = _review_step(jobs)
    assert step["uses"] == "anthropics/claude-code-action@v1"
    assert step["with"]["anthropic_api_key"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    assert "docs/REVIEW-CONTRACT.md" in step["with"]["prompt"] and "HEAD: ${{ github.event.pull_request.head.sha }}" in step["with"]["prompt"]
    args = step["with"]["claude_args"]
    schema = json.loads(re.search(r"--json-schema '(\{.*\})'", args, re.S).group(1))
    assert set(schema["required"]) == {"verdict", "head", "findings", "checked"}
    assert schema["properties"]["verdict"]["enum"] == ["PASS", "BLOCK"]


def test_the_reviewer_can_read_and_run_tests_but_never_write_not_even_a_comment(jobs):
    args = _review_step(jobs)["with"]["claude_args"]
    allowed = re.search(r'--allowedTools "([^"]+)"', args).group(1)
    assert "Bash(gh pr diff:*)" in allowed and "Bash(gh pr view:*)" in allowed and "pytest" in allowed
    assert not WRITE_TOOLS.search(allowed), allowed                  # the workflow posts the comment, not the agent


def test_the_verdict_is_posted_by_the_shared_comment_renderer_and_the_label_released(jobs):
    job = jobs["agent-review"]
    key = next(s for s in job["steps"] if s.get("id") == "key")
    assert "ANTHROPIC_API_KEY" in key["run"] and "configured=false" in key["run"]
    assert _review_step(jobs)["if"] == "steps.key.outputs.configured == 'true'"
    post = next(s for s in job["steps"] if "jr/agent_review.py comment" in str(s.get("run", "")))
    assert "--lane api" in post["run"] and post["env"]["VERDICT_JSON"] == "${{ steps.review.outputs.structured_output }}"
    assert post["if"] == "steps.key.outputs.configured == 'true'"


def test_the_code_canary_runs_on_marker_comments_reads_them_and_respects_the_kill_variable(wf, jobs):
    assert wf[True]["issue_comment"]["types"] == ["created"]
    job = jobs["code-canary"]
    assert "github.event_name == 'issue_comment'" in job["if"] and "github.event.issue.pull_request" in job["if"]
    assert "contains(github.event.comment.body, '<!-- agent-review verdict -->')" in job["if"]
    assert "vars.JR_CODE_AUTOMERGE != '0'" in job["if"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    step = next(s for s in job["steps"] if "scripts/code_canary.py" in str(s.get("run", "")))
    assert "--pr ${{ github.event.issue.number }}" in step["run"] and "--from-comments" in step["run"]
    assert step["env"]["JR_CODE_AUTOMERGE"] == "${{ vars.JR_CODE_AUTOMERGE }}"
    assert "needs" not in job                                        # the two lanes are decoupled by the comment



def test_the_api_lane_posts_with_mains_copy_of_the_poster(jobs):
    steps = jobs["agent-review"]["steps"]
    post = next(s for s in steps if "agent_review.py comment" in str(s.get("run", "")))
    assert post["run"].startswith("python3 trusted/jr/agent_review.py comment")
    trusted = [s for s in steps if (s.get("with") or {}).get("path") == "trusted"]
    assert trusted and trusted[0]["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
