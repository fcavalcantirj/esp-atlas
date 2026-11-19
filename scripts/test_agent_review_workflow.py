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
    assert wf[True]["pull_request"]["types"] == ["labeled", "synchronize"]   # synchronize only disarms (below)
    cond = jobs["agent-review"]["if"]
    assert "github.event.label.name == 'review-fallback'" in cond
    for part in ("!startsWith(github.head_ref, 'jr/tick-')", "!startsWith(github.head_ref, 'jr/research-')",
                 "github.event.pull_request.draft == false"):
        assert part in cond, part
    assert "jr/heal-" not in cond                                      # a heal PR is code: reviewed too (§1d)


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
    assert job["outputs"]["verdict"] == "${{ steps.review.outputs.structured_output }}"
    post_job = jobs["agent-review-post"]
    post = next(s for s in post_job["steps"] if "jr/agent_review.py comment" in str(s.get("run", "")))
    assert "--lane api" in post["run"] and post["env"]["VERDICT_JSON"] == "${{ needs.agent-review.outputs.verdict }}"
    assert post_job["if"] == "always() && needs.agent-review.result != 'skipped'"
    assert post["if"] == "needs.agent-review.outputs.verdict != ''"


def test_the_code_canary_runs_on_marker_comments_reads_them_and_respects_the_kill_variable(wf, jobs):
    assert wf[True]["issue_comment"]["types"] == ["created"]
    job = jobs["code-canary"]
    assert "github.event_name == 'issue_comment'" in job["if"] and "github.event.issue.pull_request" in job["if"]
    assert "contains(github.event.comment.body, '<!-- agent-review verdict -->')" in job["if"]
    assert "vars." not in job["if"]                                   # the script enforces the kill variable
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    step = next(s for s in job["steps"] if "scripts/code_canary.py" in str(s.get("run", "")))
    assert "--pr ${{ github.event.issue.number }}" in step["run"] and "--from-comments" in step["run"]
    assert step["env"]["JR_CODE_AUTOMERGE"] == "${{ vars.JR_CODE_AUTOMERGE }}"
    assert "needs" not in job                                        # the two lanes are decoupled by the comment



def test_the_api_lane_posts_from_a_fresh_job_that_never_ran_the_prs_code(jobs):
    review, post = jobs["agent-review"], jobs["agent-review-post"]
    assert review["permissions"] == {"contents": "read", "pull-requests": "read"}       # no id-token: no app token
    step = next(s for s in review["steps"] if "claude-code-action" in str(s.get("uses", "")))
    assert step["with"]["github_token"] == "${{ github.token }}" and step["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    assert not any("agent_review.py comment" in str(s.get("run", "")) for s in review["steps"])
    assert "verdict" in review["outputs"]
    assert post["needs"] == "agent-review" and post["permissions"]["pull-requests"] == "write"
    assert any("--remove-label review-fallback" in str(s.get("run", "")) and s.get("if") == "needs.agent-review.outputs.verdict == ''"
               for s in post["steps"])                                       # no verdict: the label is released
    co = [s for s in post["steps"] if "actions/checkout" in str(s.get("uses", ""))]
    assert len(co) == 1 and co[0]["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    step = next(s for s in post["steps"] if "agent_review.py comment" in str(s.get("run", "")))
    assert step["env"]["VERDICT_JSON"] == "${{ needs.agent-review.outputs.verdict }}"
    assert "${{" not in step["run"]                                        # nothing pasted into the shell



def test_every_canary_runs_one_at_a_time(jobs, wf):
    import yaml
    from pathlib import Path
    v = yaml.safe_load((Path(__file__).resolve().parent.parent / ".github/workflows/validate.yml").read_text())["jobs"]
    for job in (jobs["code-canary"], v["demand-canary"], v["tick-canary"]):
        assert job["concurrency"]["cancel-in-progress"] is False and job["concurrency"]["group"]



def test_a_push_disarms_any_queued_auto_merge_and_drops_agent_pass(jobs):
    job = jobs["disarm-on-push"]
    cond = " ".join(job["if"].split())
    assert cond.startswith("github.event_name == 'pull_request' && github.event.action == 'synchronize'")
    # Jr's AUTO-routed bookkeeping tick PR keeps its own auto-merge; a review-routed one is disarmed like any PR
    assert "!(startsWith(github.head_ref, 'jr/tick-') && !contains(github.event.pull_request.labels.*.name, 'jr-review'))" in cond
    run = job["steps"][0]["run"]
    assert '--disable-auto' in run and "--remove-label agent-pass" in run and "${{" not in run
    # the review lane never runs on a push
    assert "github.event.label.name == 'review-fallback'" in jobs["agent-review"]["if"]



# --- 2026-11-19, first live verdict (#1797): three first-run killers ---------------------------------------
# (1) every canary was SKIPPED: `vars.JR_X_AUTOMERGE != '0'` is false while the variable is unset (measured on
#     the code canary and on tick PR #1860; setting the variable to 1 made the same event run). A kill switch
#     must never be "off unless configured": no job `if` may read `vars.` — the scripts read the variable.
# (2) once it ran, code-canary crashed on `import yaml`: the job installed nothing.

def test_no_job_if_reads_a_configuration_variable(jobs):
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    for wf_path in sorted(root.glob("*.yml")):
        doc = yaml.safe_load(wf_path.read_text())
        for name, job in (doc.get("jobs") or {}).items():
            if name in ("demand-canary", "tick-canary", "code-canary"):
                assert "vars." not in str(job.get("if", "")), f"{wf_path.name}:{name}"


def test_the_code_canary_installs_what_its_imports_need(jobs):
    runs = " ".join(str(s.get("run", "")) for s in jobs["code-canary"]["steps"])
    assert "pip install" in runs and "pyyaml" in runs and "httpx" in runs
