"""Tests for .github/workflows/agent-review.yml: the API lane runs only on the runner's `review-fallback`
label, reads and reports, never writes; the code canary runs on every marker comment and merges only on a
PASS at the PR's current head, behind both switches (docs/REVIEW-CONTRACT.md, "Who runs it")."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
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
    steps = [s for s in jobs["agent-review"]["steps"] if s.get("id") == "review"]
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


def test_the_reviewer_is_the_pinned_cli_run_directly_with_the_contract_and_a_verdict_schema(jobs):
    step = _review_step(jobs)
    assert "uses" not in step and re.search(r"^\s*claude -p \"\$PROMPT\"", step["run"], re.M)
    assert step["env"]["ANTHROPIC_API_KEY"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    prompt = step["env"]["PROMPT"]
    assert "docs/REVIEW-CONTRACT.md" in prompt and "HEAD: ${{ github.event.pull_request.head.sha }}" in prompt
    assert "PR NUMBER: ${{ github.event.pull_request.number }}" in prompt and "REPO: ${{ github.repository }}" in prompt
    args = step["run"]
    for flag in ("--model claude-opus-5-5", "--max-turns 40", "--output-format json", "< /dev/null"):
        assert flag in args, flag
    schema = json.loads(re.search(r"--json-schema '(\{.*?\})' \\\n", args, re.S).group(1))
    assert set(schema["required"]) == {"verdict", "head", "findings", "checked"}
    assert schema["properties"]["verdict"]["enum"] == ["PASS", "BLOCK"]
    assert "${{" not in step["run"]                 # every event value reaches the shell through env, never spliced in


def test_the_api_lane_never_uses_the_github_action_because_it_is_billed_as_claude_code(jobs):
    """2026-11-20: the plan's monthly API credit covers the API and the Agent SDK, not Claude Code. Anthropic:
    "Runs started by the Claude Code GitHub Action ... count as Claude Code usage, so API credits don't cover
    them, even with -p"; `claude -p` run yourself with an API key "is billed as Agent SDK usage". With the
    Action every review was refused "Credit balance is too low" while $199.95 of credit sat unused."""
    steps = jobs["agent-review"]["steps"]
    assert not any("claude-code-action" in str(s.get("uses", "")) for s in steps)
    install = [n for n, s in enumerate(steps) if "npm install -g @anthropic-ai/claude-code@" in str(s.get("run", ""))]
    review = next(n for n, s in enumerate(steps) if s.get("id") == "review")
    assert len(install) == 1 and install[0] < review and steps[install[0]]["if"] == steps[review]["if"]
    assert re.search(r"npm install -g @anthropic-ai/claude-code@\d+\.\d+\.\d+\s*$", steps[install[0]]["run"].strip())   # an exact version
    node = next(n for n, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-node@"))
    assert node < install[0]


def _extractor(jobs):
    """The inline Python of the review step that turns the CLI's JSON result into the job's verdict output."""
    return re.search(r"<<'PY'\n(.*?)\nPY\b", _review_step(jobs)["run"], re.S).group(1)


def _extract(jobs, tmp_path, result, *, before=""):
    out, res = tmp_path / "out.txt", tmp_path / "result.json"
    out.write_text(before, encoding="utf-8")
    if result is not None:
        res.write_text(result if isinstance(result, str) else json.dumps(result), encoding="utf-8")
    run = subprocess.run([sys.executable, "-c", _extractor(jobs), str(res)], capture_output=True, text=True,
                         env={**os.environ, "GITHUB_OUTPUT": str(out)})
    lines = [ln for ln in out.read_text(encoding="utf-8").splitlines() if ln.startswith("structured_output=")]
    return run, lines[-1][len("structured_output="):]          # GitHub keeps the LAST value written for a name


VERDICT = {"verdict": "PASS", "head": "a" * 40, "findings": [], "checked": ["the diff\nline two"]}


def test_the_step_hands_on_the_structured_verdict_as_one_line_of_json(jobs, tmp_path):
    result = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 9, "total_cost_usd": 0.21,
              "result": "done", "structured_output": VERDICT}
    run, value = _extract(jobs, tmp_path, result)
    assert run.returncode == 0 and json.loads(value) == VERDICT and "\n" not in value
    assert '"total_cost_usd": 0.21' in run.stdout and "done" not in run.stdout          # the cost is logged, the answer is not
    run, value = _extract(jobs, tmp_path, [{"type": "system"}, result])                 # a message list: the result is the last one
    assert run.returncode == 0 and json.loads(value) == VERDICT


def test_a_refused_or_empty_review_leaves_no_verdict_fails_the_step_and_says_why(jobs, tmp_path):
    refused = {"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "total_cost_usd": 0,
               "terminal_reason": "api_error", "api_error_status": 400, "result": "Credit balance is too low"}
    run, value = _extract(jobs, tmp_path, refused)
    assert run.returncode != 0 and value == ""
    assert '"api_error_status": 400' in run.stdout and "Credit balance is too low" in run.stdout
    # an error result never yields a verdict, even if one is attached to it
    run, value = _extract(jobs, tmp_path, {**refused, "structured_output": VERDICT})
    assert run.returncode != 0 and value == ""
    for broken in (None, "", "not json", '{"type": "result"}', '{"type":"result","structured_output":"PASS"}', "[]"):
        run, value = _extract(jobs, tmp_path, broken)
        assert run.returncode != 0 and value == "", broken


def test_the_step_always_writes_the_output_last_so_nothing_written_earlier_can_stand_in_for_a_verdict(jobs, tmp_path):
    forged = "structured_output=" + json.dumps({**VERDICT, "head": "f" * 40}) + "\n"
    run, value = _extract(jobs, tmp_path, {"type": "result", "is_error": True, "result": "boom"}, before=forged)
    assert run.returncode != 0 and value == ""


def test_the_reviewer_can_read_and_run_tests_but_never_write_not_even_a_comment(jobs):
    args = _review_step(jobs)["run"]
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
    assert job["permissions"] == {"contents": "write", "pull-requests": "write", "actions": "write"}
    step = next(s for s in job["steps"] if "scripts/code_canary.py" in str(s.get("run", "")))
    assert "--pr ${{ github.event.issue.number }}" in step["run"] and "--from-comments" in step["run"]
    assert step["env"]["JR_CODE_AUTOMERGE"] == "${{ vars.JR_CODE_AUTOMERGE }}"
    assert "needs" not in job                                        # the two lanes are decoupled by the comment



def test_the_api_lane_posts_from_a_fresh_job_that_never_ran_the_prs_code(jobs):
    review, post = jobs["agent-review"], jobs["agent-review-post"]
    assert review["permissions"] == {"contents": "read", "pull-requests": "read"}       # no id-token: no app token
    step = _review_step(jobs)
    # the job's own read-only token for `gh`; the PR's tests never see a credential
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}" and step["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"
    assert not any("agent_review.py comment" in str(s.get("run", "")) for s in review["steps"])
    assert "verdict" in review["outputs"]
    assert post["needs"] == "agent-review" and post["permissions"]["pull-requests"] == "write"
    assert any("--remove-label review-fallback" in str(s.get("run", "")) and s.get("if") == "needs.agent-review.outputs.verdict == ''"
               for s in post["steps"])                                       # no verdict: the label is released
    co = [s for s in post["steps"] if "actions/checkout" in str(s.get("uses", ""))]
    assert len(co) == 1 and co[0]["with"]["ref"] == "${{ github.event.repository.default_branch }}"   # main's tip
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
    # needs-human describes a verdict (a BLOCK, or a PASS only a person may merge) at the OLD head: after a push
    # nobody was asked anything yet, and the daily line must not count the PR as waiting on a person
    assert "--remove-label needs-human" in run
    # except on a demand PR, where the label means a quote FAILED and a red quotes job skips the canary that
    # would set it again (review note on #1880)
    lines = [ln.strip() for ln in run.splitlines()]
    i = lines.index('case "$PR_BRANCH" in')
    assert lines[i + 1] == "jr/research-*) ;;" and lines[i + 2].startswith('*) gh pr edit "$PR_NUMBER"') and "needs-human" in lines[i + 2]
    assert job["steps"][0]["env"]["PR_BRANCH"] == "${{ github.head_ref }}"
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


def test_a_dispatch_is_a_sweep_and_every_canary_run_ends_with_one(wf, jobs):
    # 2026-11-19: a PASS the hourly cap made wait was never looked at again
    assert "workflow_dispatch" in wf[True]
    job = jobs["code-canary"]
    # only from main: a dispatch at another ref would run that ref's switches and canary code
    assert job["if"].replace("\n", " ").startswith(
        "(github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main') || (")
    one = next(s for s in job["steps"] if "--from-comments" in str(s.get("run", "")))
    assert one["if"] == "github.event_name == 'issue_comment'"        # a dispatch has no PR of its own
    sweep = next(s for s in job["steps"] if "--sweep" in str(s.get("run", "")))
    assert sweep["run"].strip() == "python3 scripts/code_canary.py --sweep" and sweep["if"] == "always()"
    assert sweep["env"] == one["env"]                                   # same token, same kill variable
    names = [str(s.get("run", "")) for s in job["steps"]]
    assert names.index(one["run"]) < names.index(sweep["run"]) < len(names) - 1   # then main's CI step, last


def test_no_other_job_runs_on_a_dispatch(jobs):
    for name, job in jobs.items():
        if name == "code-canary":
            continue
        cond = str(job.get("if", "")).replace("\n", " ")
        assert "github.event_name == 'pull_request'" in cond or "needs.agent-review.result != 'skipped'" in cond, name


def test_the_api_lane_proves_its_shell_sandbox_starts_before_it_reviews(jobs):
    # 2026-11-19: the lane's first run posted "BLOCK: sandbox failed to initialize, socat not installed" on #1876
    steps = jobs["agent-review"]["steps"]
    i = next(n for n, s in enumerate(steps) if "bubblewrap" in str(s.get("run", "")))
    review = next(n for n, s in enumerate(steps) if s.get("id") == "review")
    assert i < review and steps[i]["if"] == steps[review]["if"]
    lines = [ln.strip() for ln in steps[i]["run"].splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert any("apt-get install" in ln and "socat bubblewrap" in ln and "Acquire::Retries=3" in ln for ln in lines)
    assert "for attempt in 1 2 3; do" in lines                    # the mirror blinked on the first live run
    # the two proofs end the step and nothing swallows their exit code: a sandbox that cannot start fails the job
    assert lines[-2:] == ["command -v socat", "bwrap --ro-bind / / --unshare-net true"]
    assert not steps[i].get("continue-on-error")
    assert steps[review]["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"     # the reason the sandbox is required


def test_a_test_file_the_reviewer_cannot_run_is_read_and_left_to_the_required_check(jobs):
    # 2026-11-19: #1840, #1843 and #1851 were BLOCKed on "the reviewer could not run the test file" alone:
    # TypeScript tests under apps/web, which neither review lane can run and CI's required `tests` check does
    contract = (REPO / "docs" / "REVIEW-CONTRACT.md").read_text()
    prompt = (REPO / "docs" / "ops" / "REVIEW-PROMPT.md").read_text()
    step = _review_step(jobs)
    for text in (contract, prompt, step["env"]["PROMPT"]):
        flat = " ".join(text.split())
        assert "apps/web/" in flat and "gh pr checks" in flat
        assert "READ, not run" in flat or "is read, not run" in flat
    assert '"I could not run it" is never a finding' in " ".join(contract.split())
    allowed = re.search(r'--allowedTools "([^"]+)"', step["run"]).group(1)
    assert "Bash(gh pr checks:*)" in allowed
    # the web suite really is inside the required check the rule leans on
    validate = yaml.safe_load((REPO / ".github" / "workflows" / "validate.yml").read_text())
    assert any(str(s.get("run", "")).strip() == "npm test" for s in validate["jobs"]["tests"]["steps"])

