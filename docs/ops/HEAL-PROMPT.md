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
