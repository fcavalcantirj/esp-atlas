# Agent review — the delegate's instructions (subscription lane)

Status: the task text `jr/agent_review.py` hands the runner's coding delegate for one code pull request
(docs/REVIEW-CONTRACT.md is the contract; this is how you carry it out). The API lane's workflow
(`.github/workflows/agent-review.yml`) gives the same instructions to `anthropics/claude-code-action`.

## Inputs (environment)

- `REPO_SLUG`, `PR_NUMBER`, `HEAD`: the pull request and the exact commit you review. The checkout you are in
  is that commit (a detached worktree); you never switch branches.
- `VERDICT_FILE`: a path OUTSIDE the repository. Your one deliverable is the structured verdict written
  there as JSON; the runner posts it as the PR comment. Write nothing else anywhere.

## What you do

1. Read `docs/REVIEW-CONTRACT.md` and follow it exactly. Read the whole diff (`gh pr diff $PR_NUMBER
   --repo $REPO_SLUG`) and the PR body (`gh pr view $PR_NUMBER --repo $REPO_SLUG --json title,body`).
2. Match every `[TEST]` and `[REAL]` claim; run only the test files the diff adds or changes
   (`PYTHONPATH=apps/core/src python3 -m pytest <files> -q`).
3. Write the verdict to `VERDICT_FILE`:

```json
{"verdict": "PASS" | "BLOCK", "head": "<HEAD>", "findings": [{"file": "...", "line": 0, "summary": "...", "failure": "..."}], "checked": ["..."]}
```

   `head` is exactly `$HEAD`. Unsure is `BLOCK` with the doubt as a finding. If you cannot read the diff or
   run the tests, `BLOCK` with that reason; never guess `PASS`.
4. Stop. Do not comment, label, edit, commit, push or merge; the runner posts the verdict and the code canary
   acts on it.
