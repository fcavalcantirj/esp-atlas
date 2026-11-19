# CI heal — the delegate's instructions

Status: the prompt `SPEC-jr-self-heal.md` §3 names (2026-11-12). The operator's heal launcher runs a
coding delegate with this text once per incident that `python3 jr/ci_watch.py claim` hands out. One
incident per run. No host names, shell users or credential paths belong here (the repository is
public); the launcher supplies the checkout, the branch and the incident file.

## Inputs the launcher gives you

- `INCIDENT`: the path of the claimed incident as JSON (`id`, `fingerprint`, `branch`, `context`).
  `context` holds the failing `check`, the failing test node (`failed`), its first assertion line,
  the first `##[error]` line, the failing run id, the first red commit and PR, the runner image of
  the red run and of the last green run on main, the last green commit, and `log_excerpt`.
- `BRANCH`: the incident's `branch` (`jr/heal-<id>`), already checked out fresh from `origin/main`.
  You never create another branch, never merge, never push to `main`.
- `BODY`: a file path outside the repository for the PR body. The relay reads it; it is never
  committed.

## What you do, in order

1. **Read the evidence before any theory.** Read `INCIDENT`. Diff the green side against the red
   side: the commits between the last green commit and the first red one
   (`git log <last_green_sha>..<first_red_sha>`), the two runner images, and the dependency versions
   the failing job installs. Read the failing test and the code it exercises.
2. **Name the root cause** in two lists: MEASURED (what a log, a diff or a run shows) and INFERRED
   (what follows from it). If nothing you measured explains the failure, say "root cause not found",
   write what you measured, and stop at step 6 without a code change.
3. **Reproduce** on this host when it can run the failing test. When it cannot (another OS, a tool
   the runner has and this host lacks), the failing CI run is the RED: cite its run id and the
   assertion.
4. **Fix the cause, smallest change.** Fix it where it lives. A test may change only when the test is
   what is wrong, and then it must stay as strict as before: derive the exact expectation, never
   widen it to accept anything. These are refused by the relay (`python3 jr/ci_watch.py
   relay-check`), so do not try:
   - any change under `data/` or `docs/demand/`;
   - a new `pytest.mark.skip`, `skipif` or `xfail`, or `pytest.skip()`, or a deleted test file;
   - a removed `assert`, unless the PR body has a line starting `Assertion changed:` that names the
     test file and gives the evidence that the assertion was wrong;
   - a change to test selection (`conftest.py`, `pytest.ini`, or a pytest line such as `-k`,
     `--deselect`, `--ignore`, `addopts` or `testpaths` in a workflow, `pyproject.toml`, `setup.cfg`
     or `tox.ini`), unless the PR body has a line starting `Test selection changed:` that names the
     file and gives the evidence;
   - a change to workflow `permissions` or `secrets`;
   - more than 300 changed lines.
5. **Run what the failing job runs** (the same pytest selection) and the rest of the suite it
   belongs to, once each, saving the full output; quote the pass and fail counts.
6. **Commit the fix on `BRANCH` and write the PR body to `BODY`** (not into the repository):
   - the incident id and fingerprint;
   - the root cause, MEASURED and INFERRED;
   - the RED, with a run id or a local command and its output;
   - the GREEN you ran, and the GREEN the reviewer must see (the failing check passing on the same
     runner image as the red run, not skipped);
   - what the reviewer must check, including any `Assertion changed:` or
     `Test selection changed:` line.
7. **Stop.** The relay runs the relay check, pushes `BRANCH`, opens the PR labelled `jr-heal` and
   posts it for review. Review and merge belong to an independent reviewer. Never run Jr's tick,
   drain or demand runner, and never mark the incident resolved yourself: the tick does that when
   the check is green on main and on the next tick PR.

## When `INCIDENT.context.check` starts with `stall:` (a lane that produced nothing)

The break is not a red check: `INCIDENT.context.evidence` says a Jr lane (`backfill`, `firmware` =
admit + boardmap, or `topics`) had units every tick and produced nothing over the stall window
(`SPEC-jr-self-heal.md` §1b). The evidence carries the lane's yield over the window, this tick's stage
summaries and counters for that lane (e.g. `backfilled 0, skipped 0, cooling 84`), and the tick's reject
counts (`already_catalogued`, `skipped_scoring`, …). Steps 1–7 above hold with these readings:

1. **Evidence** is `docs/telemetry/yield.jsonl` (the lane's rows over the window), the stage summaries in
   the evidence and in the last tick PR bodies (`gh pr list --search "head:jr/tick-"`), and the stage's
   code (`jr/stage_backfill.py`, `jr/stage_admit.py`, `jr/stage_boardmap.py`, `jr/stage_admit_topics.py`,
   `jr/drain.py`, `jr/scorer.py`). There is no green/red diff: compare the last tick in which the lane
   produced with the first silent one (`git log` of `docs/telemetry/yield.jsonl` and the tick PRs).
2. **Root cause** candidates you must measure, not guess: the worklist is exhausted or cooling (every
   board of the lane's vendors on cooldown, every launcher repo decided), the source dried up (a topic
   search or catalog answering nothing), the scorer rejects everything (`skipped_scoring`, a vocabulary
   gap: `jr/board_names.py`), the budget is cut before the stage runs, or a bug. Name it MEASURED/INFERRED.
3. **Fix at the cause, within the same limits** (no `data/**`, no `docs/demand/**`, no test deletion or
   widening, at most 300 lines). A stage that correctly has nothing to do (cause outside the code: the
   vendor's docs gone, the launcher pool drained) is not fixed by code: write the finding instead as
   `docs/incidents/<INCIDENT id>.md` (MEASURED/INFERRED, what would change it, e.g. a resolver work item
   for the vendor, a new topic seed) and commit that alone. **Never fill a catalog field, author a record
   or widen a scorer to accept what it cannot verify**: an LLM solves code problems here, never inventory
   (`CLAUDE.md`, "North star").
4. **Prove it** with the stage's tests and, where the host can, a dry run of the tick
   (`python3 jr/tick.py --dry-run`): the would-write list must show the lane producing.
5. The incident resolves itself when the lane produces again over the yield window; never mark it.

## When `INCIDENT.context.check` starts with `abort:` (the tick keeps aborting)

The break is not a red check: the hourly tick aborted with the same reason at least twice in a row
(`SPEC-jr-self-heal.md` §1c). `INCIDENT.context.evidence.reason` is the full abort text, `consecutive` how
many ticks in a row, `first_seen`/`last_seen` when. Steps 1–7 above hold with these readings:

1. **Evidence** is the abort text itself and the code that raised it: `grep -n "raise TickAbort" jr/tick.py`
   names every abort; follow the one whose text matches into the module it calls (for the pending-PR
   inventory, `jr/pending_prs.py`). Read the data the text names, read-only: the PR (`gh pr view <n>`),
   the files committed at its head (`gh api repos/<slug>/contents/<path>?ref=<sha>`), the ledger there.
2. **Root cause** must be measured on that data: reproduce the abort by calling the raising function
   read-only against the same PR and head (no tick run), then name it MEASURED/INFERRED. A rule that fails
   closed correctly on a real inconsistency is not the bug; a rule that fails closed on data it should
   understand (2026-11-18: a September ledger record for a rejected fork under the reused id `wled`) is.
3. **Fix at the cause, within the same limits.** Never close, merge, relabel or edit a Jr PR to make the
   abort go away (closing a tick PR vetoes its firmware for 30 days), never edit `jr/proposed_ledger.json`
   or `docs/demand/**` by hand, never loosen a fail-closed check beyond the case you reproduced. A cause
   outside the code goes to `docs/incidents/<INCIDENT id>.md` (MEASURED/INFERRED, what a human must do).
4. **Prove it** with a RED test of the exact shape you reproduced, then the same read-only call against
   the live PR showing the abort gone.
5. The incident resolves itself when a tick completes; never mark it.

## When `INCIDENT.context.check` starts with `conflict:` or `review-fix:` (fix an open PR in place)

The break is an open PR, not main (`SPEC-jr-self-heal.md` §1d). `INCIDENT.context.evidence` names it: `pr`,
`pr_branch`, `pr_head` (the head you start from; the launcher checked it out for you). Your commits go on
top of `pr_head` and are pushed, fast-forward only, to `pr_branch`; no new PR is opened. The relay check
runs with `--pr-fix`: it counts only your commits (a merge of `main` counts only its conflict resolution)
under the same limits (no `data/**`, no `docs/demand/**`, no test deletion or skip, at most 300 lines).

- **`conflict:`** — GitHub reports the PR conflicting with `main`. Merge `origin/main` into the branch
  (never rebase, never force) and resolve every conflict so that BOTH sides' intent survives: the PR's
  change and what `main` changed meanwhile. A file both sides only added to (two CI jobs, two test blocks,
  two switches) keeps both additions, each verbatim. Change no behaviour beyond the resolution: the merge
  and its resolution are the whole job. If your own tooling then objects to something `main` brought in
  (a file that is large on `main`, a style rule), say so in BODY and stop; do not refactor or split files
  (2026-11-19: a 6-line resolution grew a 516-line file split, and the relay refused all of it). Run the
  tests of every file you touched and the suites of the PR's own files; quote the counts in BODY.
- **`review-fix:`** — the agent review BLOCKed the PR at `pr_head`; `evidence.findings` lists why. Fix
  exactly those findings at their cause, with a RED test first where a finding is a behaviour, and nothing
  else. A finding you measure to be wrong is answered in BODY with the evidence, not "fixed". The agent
  review judges your new head; the third BLOCK on the same PR goes to a human.
  **A finding about the PR description** (its file reads `PR body` / `PR #n body`, or it says a `[TEST]` or
  `[REAL]` claim does not hold) is fixed in the description, not in BODY: the launcher gives you the current
  description as the file `PR_DESCRIPTION` (see "This run"). Edit that file in place and the relay replaces
  the PR description with it after your push. Rules for it: `[REAL]` only on something already observed, with
  where and when; a check still to be made after merge or deploy is written as a plan with no `[REAL]` tag
  ("Acceptance (to observe after deploy)"); `[TEST]` only on a test that is in the diff or the tree and that
  you ran; a local measurement is called a measurement; when your code fix changed how the PR works, the
  description says the new mechanism. Remove a claim only when it is false, never to make the review easier.
  When nothing but the description needs fixing, commit with `git commit --allow-empty` (subject
  `chore: PR description corrected, no code change`): the verdict is tied to the head, so without a new
  head the PR is never reviewed again.
- **`ci-fix:`** — a required check (`evidence.check`) is red on this code PR at `pr_head`, after one rerun and
  with `main` merged in; `evidence.failed` / `evidence.assertion` / `evidence.log_excerpt` say where. Reproduce
  the failing node on the PR's head, fix the PR's code at the cause (RED first if it is behaviour), never by
  deleting, skipping or loosening a test unless the test itself is wrong (then `Assertion changed:` in BODY).
- Never close, merge, retitle or relabel the PR; never touch another PR's branch.

## The machine you run on

Run every test with the interpreter named `PYTHON` in "This run": pytest and the test dependencies CI installs
are in it. Never create a virtualenv, and never write under `/tmp`: it is a small RAM disk shared with every
other job (2026-11-19: leftover virtualenvs of ~320 MB each filled it, and no review could start). Scratch
files go in the `scratch` directory beside INCIDENT, which the launcher owns.

## When `INCIDENT.context.check` starts with `pr-red:` (a Jr catalog PR is red; fix MAIN)

A Jr tick or demand PR (`evidence.prs`) is red on the required check `evidence.check` at a head that already
has `main` merged in and was rerun once, so it is neither a flake nor something `main` already fixed.
`INCIDENT.context` carries the failing node (`failed`), its assertion and the log excerpt. The PR's catalog
data is not yours to change: an LLM never writes records. Your branch starts from `main`, like any heal.

1. Reproduce on the PR's head (`gh pr checkout` in a scratch worktree, or `git show <head>:<path>`), run
   the failing node, quote the RED.
2. Decide, measured: **(a)** main's code or test is wrong for valid catalog growth (2026-11-19: three tests
   pinned an exact recipe set with `==`, so every new recipe turned CI red; the fix was `>=`, intent kept)
   → fix main, with the assertion change named in BODY (`Assertion changed:`); **(b)** the PR's record is
   really wrong (a guard or schema rule caught a bad value) → change no code; write
   `docs/incidents/<INCIDENT id>.md` (MEASURED: which record, which rule, why) and commit that alone: the
   reviewed content canary or a human closes the PR.
3. Prove it: the failing node passes on the PR's content with your change (run it in the scratch worktree
   with your files copied in), and the suites of every file you touched pass on main.
4. After your heal merges, the chores merge `main` into the red PR once more and its CI reruns; the
   incident resolves when no open PR has shown that failure for two passes in a row.

