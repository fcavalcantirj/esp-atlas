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

### 1b. A silent lane is a break too (2026-11-17)

Measured over the 160 tick PRs of 2026-11-10 → 11-17: backfill produced 0 in 160/160 ticks; a 51-tick
zero streak across every lane (Nov 15 21Z → Nov 17 23Z) raised nothing but a Telegram line. The yield
ledger (`SPEC-data-completion.md` "Yield") now says, each tick, whether a lane that had units produced
over the stall window (`jr/steering.json`: `yield.stall_ticks` 24, `yield.topics_stall_ticks` 48). A lane
silent over a full window is an incident of kind `stall` (`jr/ci_watch.stall_watch`, run after the
stages): `check` = `stall:<lane>`, fingerprint = sha256 of the lane (one break = one incident while it is
live; a recurrence after resolution gets the `-N` suffix), `evidence` = the lane's yield over the window,
this tick's stage summaries and counters for the lane, the tick's reject counts. It enters the SAME store,
`claim`, daily budget, `ack` halt and `jr-heal` review route as a red check; the delegate's prompt
(`docs/ops/HEAL-PROMPT.md`, "When `check` starts with `stall:`") diagnoses from the yield rows first and
either fixes the stage at the cause or writes the finding to `docs/incidents/<id>.md` when the cause is
outside the code. The incident resolves when the lane produces again over the yield window
(`Store.resolve_producing`). Nothing here may fill inventory: an LLM solves code problems, never records.

### 1c. A tick that keeps aborting is a break too (2026-11-18)

Measured: four hourly ticks in a row (Nov 18, 18Z → 21Z) aborted on the same pending-PR gap (a stale
ledger record under a reused firmware id) and nothing reacted but a Telegram line. An aborted tick writes
no yield rows, so §1b cannot see it, and CI was green. Every hourly tick now hands its outcome to
`jr/ci_watch.abort_watch` after its worktree and lock are released: the abort reason, the degraded reason
(an incomplete pending-PR inventory no longer aborts; it skips the firmware stages, `SPEC-jr-review-routing.md`
§6, and counts here like an abort), or nothing when it completed. Its kind is the reason's head (`pending-pr-inventory-incomplete`, `typeerror`, `guard-red`,
`terminated-by-sigterm`), and the fingerprint is sha256 of the kind: a tick stuck on the same check is one
break even when the detail changes each hour (another firmware in the gap, other files in a red guard). The
**second consecutive** abort of one kind is an incident: `check` = `abort:<kind>`, `evidence` = the latest
full reason, the streak count, first and last seen. It enters the
SAME store, `claim`, daily budget, `ack` halt and `jr-heal` review route as a red check (it is not gated
by `stall_dispatch`). Aborts the delegate cannot fix never open one and never break a streak: GitHub
unreadable or rate-limited (`gh …`, `GitHub rate limit low`), the tick lock, the call budget, branch
protection, and a tick PR open too long (that one already says it needs a human). A completed tick ends
the streak and resolves every live abort incident (`Store.resolve_aborts`). The delegate's prompt
(`docs/ops/HEAL-PROMPT.md`, "When `check` starts with `abort:`") fixes the code that raised the abort; it
never closes or merges a Jr PR to make the abort go away.

### 1d. The chores on open PRs (2026-11-18)

Owner, Nov 18: "make jr automatically do chores. site must be self sufficient." Measured that night: 31 open
PRs, 25 code PRs waiting on one human reviewer, 8 conflicting with main and resolved by hand, every agent
BLOCK waiting for a person, stacked PRs retargeted by hand. Now:
- **Retarget** is GitHub's own: `delete_branch_on_merge` is on, so a stacked PR moves to `main` when its base
  merges.
- **`jr/chores.py`**, run by every hourly tick after its own work (even after an abort): a code PR (same
  repository, not draft, based on `main`, not `jr/tick-*` — `review_refresh` owns those — nor
  `jr/research-*` — the demand retry owns those) that GitHub reports DIRTY is a `conflict:#n` incident; a PR
  labelled `needs-human` whose newest agent verdict for its CURRENT head is BLOCK is a `review-fix:#n`
  incident carrying the findings. Evidence: `pr`, `pr_branch`, `pr_head`. Fingerprint = kind + PR, so the
  same PR failing twice after a fix goes to a human (`MAX_PER_FINGERPRINT`).
- **A red required check on any open PR** (2026-11-19: tick PR #1828 sat red on `tests` all day; the CI
  watch only declares a tick break when the two newest tick PRs fail alike), once per PR and failing test, in order:
  rerun the failed jobs (a flake clears itself); still red and behind `main` → merge `main` in through
  `PUT /pulls/<n>/update-branch` with `expected_head_sha` (the fix may already be on `main`); still red and
  up to date → a Jr tick/demand PR is ONE `pr-red:` incident per failing test (fingerprint = check + node +
  assertion), healed on `main` by the CI launcher: the delegate fixes main's code or test, never the data,
  and writes a finding when the record itself is wrong; a code PR is a `ci-fix:#n` PR-fix. Non-required
  checks (`sources-live`) and cancelled/timed-out runs are never a chore. The rerun and the merge of
  `main` happen once per PR, check and failing test node (never per head: `main` moves hourly, and a key that
  changes every run would loop). A `pr-red:` incident resolves when
  no open PR shows that failure.
- **Mergeability is read until GitHub has computed it** (2026-11-19, measured: the first listing after `main`
  moved read UNKNOWN for 17 of 25 PRs; 12 s later 6 were CONFLICTING; #1835/#1836 stayed conflicting 14 h while
  `review_refresh`'s dry run said `would_refresh`). `chores.list_settled` re-reads a listing with UNKNOWN in it
  (10 s apart, 3 listings at most); the tick's preflight listing uses it too. A PR still UNKNOWN is not judged.
- **The labels the machine needs exist:** once a UTC day the chores create any of `agent-pass`, `needs-human`,
  `review-fallback`, `jr-heal` the repository lacks (all four were missing on 2026-11-19; every
  `gh pr edit --add-label` would have raised).
- **`disarm-on-push` leaves Jr's AUTO-routed tick PR alone** (a `jr/tick-*` PR without `jr-review`): its
  auto-merge is the bot's own and a push to it is the bot's refresh or the chores' merge of `main`.
- **Dispatch** only through `ci_watch.py claim --pr-fix` (a launcher that checks out `pr_head`, pushes the
  delegate's commits fast-forward to `pr_branch`, opens no PR) and the `pr_fix_dispatch` switch
  (`jr/autonomy.json` + `JR_PR_FIX_DISPATCH`), against its own budget of `PR_FIX_DAILY` (4) a UTC day.
  `relay-check --pr-fix` judges only the delegate's first-parent commits; a merge counts only its conflict
  resolution (`git show --remerge-diff`), never what `main` brings.
- **Progress**: a dispatched fix whose PR has a new head is `pushed` (the agent review re-judges it); none
  after `STALL_HOURS` is stalled; a cleared condition or a closed PR resolves the incident. **PR fixes never move the human-ack brake**: they are bounded by their own daily budget and per PR
  (one fix + one recurrence, then a human). A merged CI-heal PR (`jr/heal-*`) resets the brake.
- **Heal PRs are code**: the agent review covers `jr/heal-*` too; only tick and demand PRs have their own
  canaries.
- **The owner's audit and the scoreboard**: once a UTC day from 12Z one Telegram line. The scoreboard
  measures **Jr, not people** (2026-11-19): a day is self-sufficient when no person merged one of Jr's own
  PRs (`jr/tick-*`, `jr/research-*`, `jr/heal-*`) in the last 24 h, none of Jr's own PRs waits (`needs-human`,
  or open a day), and no incident is stuck (`needs_human`, stalled, a halted heal). People merging and holding
  their own PRs is ordinary work: the line shows it ("people's own: N merged, M open (K blocked by review)"),
  and it never breaks a day. **And the catalog grew** (2026-11-21): the day's row in
  `docs/telemetry/data-trend.jsonl` is larger than the newest row before it, counting firmware, recipes,
  boards and filled board fields (`chores.catalog_growth`). Nov 20 had 36 merges by Jr, none by a person and
  nothing waiting, yet every one was bookkeeping and every lane yielded 0 for 24 ticks; by merges alone it was a
  good day. No trend row for the day, or an unreadable file, proves nothing, so the day is not self-sufficient.
  The line says "catalog +N (yesterday→today)" or "catalog did not grow". Seven such days in a row is the claim
  "self-sufficient", and nothing less is.

### 1e. A canary that said "not now" is asked again (2026-11-19)

A canary (`scripts/demand_canary.py`, `scripts/tick_canary.py`) runs only on a pull-request event. A Jr content
PR it did not merge — capped for the day, a quoted page that did not answer, a guard since fixed on main — was
never looked at again: the chores skip `jr/research-*` and `jr/tick-*`, and the tick refreshes only its own
conflicting tick PRs. Measured: demand PR #1846, judged once on Nov 18 and waiting since.

`jr/chores.py canary_retry`, every tick, oldest PR first, at most **once per PR per UTC day** and **two per
tick**, only for a lane whose switch in `jr/autonomy.json` is true:

- a demand PR behind main is merged with main (`PUT …/update-branch` at the exact head): a new event, so main's
  current guards and canary judge it;
- otherwise, when the canary was skipped because a job it needs failed, the failed jobs of that run are rerun
  (the canary follows); when the canary did run, the canary job alone is rerun, whatever failed beside it;
- a review-routed tick PR is only ever rerun; `jr/review_refresh.py` owns its merges with main.

Left alone: `needs-human`, a red required check on a PR that is not a draft (that is `red_prs`, which never
looks at drafts), checks still running, no run at all, a PR without its lane's canary check, a fork, another
base, an AUTO-route tick PR, a PR whose fix the delegate is working on. Only failures in the canary's own run
count. Memory: `canary_retry` in the incident store, written **before** each call, so a retry that was sent,
refused, or cut short by the tick's call budget is never sent twice in a day; it runs after the actions
`red_prs` already remembered. No delegate, no model.

### 1f. Jr's own tick PRs never wait for a person (2026-11-19)

A review-routed tick PR merges by itself when `scripts/receipt_guard.py` vouches for every recipe it adds (the
tick canary, four a day since 2026-11-21). One the guard cannot vouch for used to sit open until a person read it (four of them,
25 to 38 hours old, on Nov 19). `jr/chores.py expire_tick_prs`, every tick: a `jr/tick-*` PR labelled
`jr-review`, open 72 h (`EXPIRE_HOURS`), is checked by the same guard once more (branch fetched, live
upstream); when it still cannot vouch for it, Jr closes the PR with the guard's reasons, at most two a tick,
oldest first. Closed unmerged is the existing 30-day veto (`jr/pending_prs.py`), so the same unverifiable
thing is not proposed every hour. An eligible PR is never closed (it waits for the canary's daily slot); an
unreadable git or upstream closes nothing. The daily line shows Jr's open PRs as "Jr's own queue" and does not
count them as waiting on a person; only `needs-human` on one of Jr's PRs, or a stuck incident, does.

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
- **Gate (owner, 2026-11-19: "autonomous, subscription with API fallback"):** the agent review
  (`jr/agent_review.py`, a fresh reviewer run that is not the delegate's session) judges the heal PR at its exact
  head like any code PR, and the code canary merges a PASS (`code_automerge` + `JR_CODE_AUTOMERGE`, one an hour,
  `--match-head-commit`). A BLOCK is a `review-fix:` chore: one fix and one recurrence, the third BLOCK goes to a human.
- The tick marks the incident `resolved` when the required check is green on main and on the next
  tick PR, and records time to detect, time to PR and time to green.

## 5. No loop: limits, timeouts and the owner's nudge

**Jr never parks work on a person (owner, 2026-11-19).** Each limit below used to end in "needs a human".
Each now ends by itself: a pause runs out, a stalled job gets one more try, and what fails twice is given
up with one line to the owner. The daily budgets bound the cost; nothing waits for anyone.

Owner, 2026-11-12: "make sure we won't loop … timeouts and how many times it can be called without a
human intervention, telegram nudge to me". Every limit is enforced in `jr/ci_watch.py`, not by a
prompt:

| Limit | Value | When reached |
|---|---|---|
| Dispatches per break (fingerprint) | 2: the first time, and one recurrence after its fix merged | the 3rd occurrence is recorded `abandoned` (given up): never dispatched, one Telegram line, and for a PR one comment (Jr's own heal PR is closed). The break is not recorded again for 7 days (`ABANDON_DAYS`); after that it counts afresh |
| Dispatches without a merged fix | 3 (`MAX_AUTO_WITHOUT_ACK`) | `claim` pauses the lane until the next UTC day, then resumes by itself; a merged heal PR or `python3 jr/ci_watch.py ack` resumes it at once |
| A stall incident (§1b) while `jr/autonomy.json` has `stall_dispatch: false`, or the runner variable `JR_STALL_DISPATCH=0` | `claim` never hands it out (it stays `open`, visible in `show` and the nudge); CI incidents are unaffected. The flag turns on by a reviewed PR; the variable is the instant kill (2026-11-18) |
| Dispatches per UTC day | 2, all breaks together (the CLI clock is UTC; a timestamp with any offset is counted on its UTC day) | the next day |
| Same incident seen again while live | 0 new records | nothing: one record per break, whatever the number of red ticks |
| Time from dispatch to a heal PR | 4 h (`STALL_HOURS`) | `stalled`; opened once more 24 h later (`RETRY_AFTER_HOURS`); a second stall is `abandoned` |
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
  - (§1b, `jr/test_ci_watch_stall.py`, `jr/test_tick_dry_run.py`) a lane silent over the stall window is one
    `open` stall incident with the tick's evidence, not a second one next tick; the lane producing again
    resolves it and a later silence is `-2`; the launcher claims it like a CI incident; a dry run records
    nothing; the first tick after merge (no rows) runs no stall watch;
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

(Auto-merging a heal PR moved into scope on 2026-11-19: see §4 "Gate" and §1d.)
