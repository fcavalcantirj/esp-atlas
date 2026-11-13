# SPEC — Jr self-heal: a red required check becomes a reviewed fix, automatically

> **Status:** spec, 2026-11-12. Owner ask (2026-11-12): "Atlas Jr deals with this … dispatch Claude
> Code to investigate and fix when an unknown thing happens, automatic."

## Why

On 2026-11-12 GitHub moved `ubuntu-latest` from `ubuntu-24.04` to `ubuntu-26.04`. The new image
ships bubblewrap, so the image-sandbox tests ran in CI for the first time and one assertion that
assumed the runner Pi's directory layout failed. From 12:00Z every hourly tick PR was red on
`jr-tests`, no tick could merge, and main stopped at 11:34Z. Jr kept opening a PR every hour and
closing the previous one as superseded. Nobody knew until a manual review six hours later.

Jr reads no CI result anywhere (`git grep` for `statusCheckRollup`, `conclusion`, `check_runs` in
`jr/*.py` on 2026-11-12: nothing). The operator's coding delegate (Claude Code through the Claude
Agent SDK, already used by `SPEC-demand-work-consumer.md`) and the relay that pushes its branch and
opens the PR already exist. What is missing is detection, a deterministic first response, and a
dispatch contract. This spec adds those three and changes no review gate.

## 1. Detection — deterministic, every tick (`jr/ci_watch.py`)

Runs in the tick's preflight, after the open-PR triage, from the same GitHub reads. It never aborts
the tick: a red CI wastes a tick PR but does not make the tick unsafe.

- **Required checks** are read from branch protection on `main` (today `schema`, `tests`,
  `jr-tests`), never hard-coded. The source is `GET repos/<slug>/branches/main`
  (`protection.required_status_checks.contexts`), which any token that can read the repo may call. The
  dedicated `.../protection/required_status_checks` endpoint needs admin rights: it answered the tick's
  own token 404 on every tick from 2026-11-12 to 2026-11-13, so it is only the fallback.
- **Evidence read:** the required checks of (a) the newest completed `validate` run on `main` and
  (b) the newest three tick PRs, open or closed as superseded, with their head SHAs.
- **Incident** when a required check concluded `failure` on main, or on two consecutive tick PRs
  with the same fingerprint (below). Two tick PRs carry different content, so one failure shared by
  both points outside either PR. `cancelled`, `timed_out` and `startup_failure` are infrastructure
  (§2), never an incident by themselves.
- **Fingerprint** = sha256 of the check name, the first failing test node id (pytest
  `FAILED <nodeid>`) or the first `::error::` line, and the assertion's first line with
  numbers, hex and paths under the runner's work directory blanked out. The fingerprint is stable
  across the tick PRs of one incident (on 2026-11-12, six runs gave one fingerprint) and differs
  between different breaks.
- **Context captured with it:** the last green run on main and the first red one (ids, SHAs), the
  commit range between them, both runner images (`Image:`/`Version:` lines of the job log), and the
  failing job's log cut to the failure block (at most 200 lines).

## 2. Known causes — handled in code, no model

| Signal | Action |
|---|---|
| A required check `cancelled` / `timed_out` / `startup_failure`, or a job log with a GitHub 5xx or "runner lost" line | re-run the failed jobs once per run (`gh run rerun --failed`); twice in a row is an incident |
| The failure is in a non-required check (`sources-live`) | ignored: it already has its own tracker |
| The red tick PR is the only red and main is green | not an incident: the PR's own content is the suspect, and review routing handles it |

Anything else is an **unknown cause** (§3). The table grows only by a reviewed spec change, each new
row with the incident that taught it.

## 3. Unknown cause — dispatch the coding delegate

- **Incident record** (runner-local state, outside the repo because the repo is public; the tick and
  the operator's launcher both write it, so every load-modify-save holds an exclusive `flock` on a
  sidecar `<store>.lock`, and the store is replaced atomically from a per-process temporary file): fingerprint,
  first seen, context (§1), state `open → dispatched → pr_opened → resolved`, or `needs_human` /
  `stalled` (§5). One record
  per fingerprint. A record still open when the same fingerprint appears again is not re-dispatched.
- **Hand-off:** the tick writes the record. An operator-side launcher (the same mechanism that runs
  the demand executor) picks up `open` records within the hour and launches the delegate detached,
  so a tick never waits on it.
- **Branch:** `jr/heal-<first 12 hex of the fingerprint>`, fresh from `origin/main`.
- **Prompt:** `docs/ops/HEAL-PROMPT.md` plus the incident context. The delegate must:
  1. name the root cause from evidence: diff the green and red run (commits, image, dependency
     versions, log), and say which is MEASURED and which is INFERRED;
  2. reproduce where the host can, otherwise cite the failing CI run as the RED;
  3. make the smallest fix at the cause, run the suites the failing job runs, and commit;
  4. write the PR body: cause, evidence, RED, GREEN expectation, and what the reviewer must check.
- **Hard limits** (the relay refuses a branch that breaks one and posts why): no change under
  `data/**` or `docs/demand/**`; no new `skip`, `skipif`, `xfail` or deleted test; no removed
  `assert` unless the PR body names that assertion and shows with evidence why it was wrong; no change
  to test selection (`conftest.py`, `pytest.ini`, or a pytest line such as `-k`, `--deselect`,
  `--ignore`, `addopts`, `testpaths` in a workflow, `pyproject.toml`, `setup.cfg` or `tox.ini`)
  unless the PR body has a `Test selection changed:` line naming the file with evidence; no
  change to workflow `permissions`, secrets, branch protection or `required` checks; at most 300
  changed lines; never merge, never run Jr's tick, drain or demand runner.
- **No root cause found:** the delegate commits nothing to code and writes its findings. The relay
  posts them in the coordination room and the incident stays `dispatched` for a human or agent.

## 4. Relay, review, merge

- The relay pushes the branch, opens the PR labelled `jr-heal` (always the REVIEW route), and posts
  in the coordination room and the operator's notification channel within the hour.
- **Gate unchanged:** an independent exact-head reviewer who is not the delegate, merged with
  `gh pr merge --match-head-commit`. Jr never merges a `jr-heal` PR.
- The tick marks the incident `resolved` when the required check is green on main and on the next
  tick PR, and records time to detect, time to PR and time to green.

## 5. No loop: limits, timeouts and the owner's nudge

Owner, 2026-11-12: "make sure we won't loop … timeouts and how many times it can be called without a
human intervention, telegram nudge to me". Every limit is enforced in `jr/ci_watch.py`, not by a
prompt:

| Limit | Value | When reached |
|---|---|---|
| Dispatches per break (fingerprint) | 2: the first time, and one recurrence after its fix merged | the 3rd occurrence is recorded `needs_human`, never dispatched, and stays human-only for good |
| Dispatches without a human | 3 since the last `python3 jr/ci_watch.py ack` on the runner | `claim` halts the lane; nothing is dispatched until a human acks |
| Dispatches per UTC day | 2, all breaks together (the CLI clock is UTC; a timestamp with any offset is counted on its UTC day) | the next day |
| Same incident seen again while live | 0 new records | nothing: one record per break, whatever the number of red ticks |
| Time from dispatch to a heal PR | 4 h (`STALL_HOURS`) | `stalled`, never retried automatically |
| Delegate run | the operator's wall-clock cap (`MAX_WALL_SECONDS` of the delegate) | the run ends; no PR, so the 4 h stall rule applies |
| The tick itself | the runner's tick `timeout`; every GitHub read in the watch fails open | the tick goes on; the report says `ci_watch unavailable` |
| A blind watch | 3 consecutive `unavailable` ticks (`BLIND_AFTER`) | one "CI watch blind" nudge, then at most one per UTC day until a tick reads CI again |

So with no human at all, the lane makes at most 3 dispatches, then stops and says so.

**Telegram nudge.** Every state change of an incident sends exactly one message to the owner's
Telegram through the tick's notifier: opened, dispatched, PR open, resolved, `needs_human`,
`stalled`, and the halt (once, naming the `ack` command). An hour with no change sends nothing. A dry
run and `--no-telegram` send nothing. A watch that cannot see CI says so too: the third `unavailable`
tick in a row sends "CI watch blind" with the reason, at most once per UTC day, and the first tick that
reads CI again ends the streak (2026-11-13: 23 silent `unavailable` ticks were found only by the
weekly review).

## 6. Acceptance

- **Offline, deterministic** (`jr/test_ci_watch.py`, fixtures from the 2026-11-12 runs):
  - six red tick PRs with the same failing nodeid give one fingerprint and one `open` record on the
    second red PR;
  - one red PR with green main gives no incident;
  - `cancelled` gives one rerun and no incident, and two in a row give an incident;
  - different nodeids give different fingerprints;
  - a closed incident's fingerprint coming back is `-2`, and a third time `needs_human`;
  - three dispatches without an `ack` halt `claim` until `ack`; a dispatch with no PR after 4 h is
    `stalled` and never handed out again;
  - every state change yields one nudge, a repeat hour none, and a dry run sends nothing;
  - a branch that adds `pytest.mark.skip`, touches `data/**`, deselects a test through
    `conftest.py`, `pytest.ini` or a workflow pytest line, or exceeds 300 lines is refused by the
    relay check;
  - a stale writer (the tick) that loaded before the launcher's `claim` cannot undo that claim;
  - every GitHub read failure leaves the tick running and records "ci_watch unavailable" in the
    report;
  - the required checks are read with a token that gets 404 from the protection endpoint (the
    runner's real case), and the protection endpoint is the fallback;
  - three blind ticks nudge once, a fourth the same UTC day nothing, the next UTC day once more; a
    tick that reads CI resets the streak; a dry run counts nothing.
- **Real:** the first natural incident end to end: detection within one tick of the second red tick
  PR, one dispatch, a `jr-heal` PR, an independent review, merge, green main. Until then the lane is
  unproven, however many fixtures pass.

## Not in scope

Auto-merging a heal PR. A second review agent with auto-merge may follow after three natural heals
were merged without a reviewer change, as its own spec.
