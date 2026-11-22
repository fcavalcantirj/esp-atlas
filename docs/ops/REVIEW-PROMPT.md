# Agent review — the delegate's instructions (subscription lane)

Status: the task text `jr/agent_review.py` hands the runner's coding delegate for one code pull request
(docs/REVIEW-CONTRACT.md is the contract; this is how you carry it out). The API lane's workflow
(`.github/workflows/agent-review.yml`) gives `claude -p` the same contract with its own
inline prompt (no "This run" block: that lane writes no verdict file).

## Inputs (environment)

- `REPO_SLUG`, `PR_NUMBER`, `HEAD`: the pull request and the exact commit you review. The checkout you are in
  is that commit (a detached worktree); you never switch branches.
- At the END of this text, under "This run": `VERDICT_FILE`, `CONTRACT_FILE` and `REVIEW_PYTHON`. They are
  given as text, not as environment variables (the PR's own code must not find the verdict path).
  `VERDICT_FILE` is a path OUTSIDE the repository: your one deliverable is the structured verdict written
  there as JSON; the runner posts it as the PR comment. Write nothing else anywhere.

## What you do

1. Read the contract at `CONTRACT_FILE` (main's copy; never the checkout's own, which the PR may have changed
   or may predate) and follow it exactly. Read the whole diff (`gh pr diff $PR_NUMBER
   --repo $REPO_SLUG`) and the PR body (`gh pr view $PR_NUMBER --repo $REPO_SLUG --json title,body`).
2. Match every `[TEST]` and `[REAL]` claim; run only the test files the diff adds or changes
   (`PYTHONPATH=apps/core/src <REVIEW_PYTHON> -m pytest <files> -q`; do not look for another interpreter).
   A changed test file under `apps/web/` (TypeScript) is READ, not run: this machine has no Node setup for it,
   and the required check `tests` runs the whole web suite at the PR's head before anything can merge. Check
   that the test tests what the claim says and look at `gh pr checks $PR_NUMBER --repo $REPO_SLUG`: `tests`
   failed at this head is a finding; pending is not, and "could not run it" is never a finding for these files.
3. Write the verdict to `VERDICT_FILE`:

```json
{"verdict": "PASS" | "BLOCK", "head": "<HEAD>", "findings": [{"file": "...", "line": 0, "summary": "...", "failure": "..."}], "checked": ["..."]}
```

   `head` is exactly `$HEAD`. Unsure is `BLOCK` with the doubt as a finding. If you cannot read the diff or
   run the tests, `BLOCK` with that reason; never guess `PASS`. The tooling around you may afterwards report
   that the repository's own test run failed in its environment: that is not yours to fix. Change no file and
   do not rewrite your verdict because of it.
4. Stop. Do not comment, label, edit, commit, push or merge; the runner posts the verdict and the code canary
   acts on it.
