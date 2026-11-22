# Review contract — what an independent reviewer of an esp-atlas pull request does

This is the exact-head review practised in the project's coordination room since 2026-11-04, written down
so a machine can run it. It applies to every pull request that is not a `jr/tick-*` or `jr/research-*`
branch (those have their own machine reviews: the receipt guard and the demand guard). The reviewer is
independent of the author: it never edits the branch, it only reads, runs and reports.

## What the reviewer reads

1. The **exact head**: the commit the PR points at when the review starts (`gh pr view --json headRefOid`).
   The verdict names that sha. A later push is a new review.
2. The **whole diff** (`gh pr diff`), every file, not the description's summary of it.
3. The **PR body's claims**: every `[TEST]` claim must match a test that exists in the diff or the tree
   and runs; every `[REAL]` claim must be stated as an observation with a where and a when, never as an
   intention. A claim that cannot be matched is a blocking finding.
4. The repository's own rules: `CLAUDE.md` (cite-or-omit, derived ≠ quoted, deterministic where it
   matters), `AGENTS.md`, and the spec that owns the touched area (`SPEC-INDEX.md` says which).

## What the reviewer runs

- The test files the diff adds or changes: `PYTHONPATH=apps/core/src python3 -m pytest <those files> -q`.
  Failing tests are blocking. (The full suites run in CI; the reviewer does not repeat them.)
- **A test file the reviewer's machine cannot run** (the web app's TypeScript tests under `apps/web/`: they
  need Node and the app's installed dependencies, which neither review lane has) is read, not run. The
  required check `tests` runs the whole web suite (`npm test`) at the PR's head, and no PR merges before
  that check is green at exactly the reviewed head. So the reviewer checks that the test exists and tests
  what the claim says, and looks at `gh pr checks <n> --repo <slug>`: `tests` **failed** at this head is a
  blocking finding; pending or not yet run is not, and "I could not run it" is never a finding for these
  files (2026-11-19: #1840, #1843 and #1851 were blocked on nothing else).
- Nothing that writes: no commits, no pushes, no merges, no label changes, no deletions. No network beyond
  `gh pr view`, `gh pr diff`, `gh pr comment`.

## What is a blocking finding

- A correctness defect the diff introduces, with the concrete input that triggers it.
- A data record that asserts a hard spec without a cited live source, or with a quote the cited page does
  not hold (cite-or-omit).
- A change to Jr's write paths that bypasses `jr/work_record.py`, `jr/memory.py` or the ledger guard.
- A test the PR body claims that does not exist, does not run, or does not test the claim.
- A secret, token, host name, shell user or credential path added to this public repository.
- A workflow change that removes or weakens a required check, a switch or a cap without saying so.

Style, naming, wording and "I would have done it differently" are not findings. A finding without a
concrete failure scenario is not a finding.

## The verdict

One structured answer, nothing else decides:

```json
{"verdict": "PASS" | "BLOCK", "head": "<sha>", "findings": [{"file": "...", "line": 0, "summary": "...", "failure": "..."}], "checked": ["..."]}
```

- `PASS`: no blocking finding at this head; `checked` lists what was read and run.
- `BLOCK`: at least one blocking finding, each with its file, line, one-sentence summary and the concrete
  failure scenario. The reviewer posts the findings as one PR comment so the author can act.
- Unsure is `BLOCK` with the doubt written down. A reviewer that cannot read the diff or run the tests
  answers `BLOCK` with that reason; it never guesses `PASS`. (A test file its machine cannot run is covered
  by the rule in "What the reviewer runs", not by this one.)

## What happens with the verdict

`PASS` lets the code canary request the merge at that exact head, when the repository's switches allow
(`jr/autonomy.json` `code_automerge`, repository variable `JR_CODE_AUTOMERGE`), at most one such merge an
hour, after every required check is green. `BLOCK` labels the PR `needs-human`; nobody waits — the author's
next push starts a new review. A person audits merged PRs after the fact and holds the kill switch.

## Who runs it (owner, 2026-11-18: "subscription and api as fallback")

- **Primary: the runner's coding delegate on the Claude subscription** (`jr/agent_review.py once`, hourly on
  the runner, `docs/ops/REVIEW-PROMPT.md` as the task). It reviews the next open code PR without a verdict
  for its current head (first one that was reviewed before and has a new head, a fix waiting to be judged;
  then the oldest update), in a detached worktree at that head, read-only, and posts the verdict as ONE comment
  that begins with the marker `<!-- agent-review verdict -->` (lane `subscription`).
- **Fallback: GitHub Actions with the API key**, only when the primary lane reports it is DOWN (no
  subscription token, usage limit, auth failure). The runner then labels that PR `review-fallback`, at most
  three a UTC day; the label triggers `.github/workflows/agent-review.yml`, which runs
  the Claude Code CLI directly (`claude -p`) with `ANTHROPIC_API_KEY` for that PR alone and posts the same comment (lane
  `api`), then removes the label. A busy delegate is not a down lane: the PR waits an hour.
- **The verdict comment is the one source of truth**: the code canary reads the newest marker comment naming
  the PR's current head, whichever lane wrote it. A later push needs a new comment.
