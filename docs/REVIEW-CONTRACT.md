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
  answers `BLOCK` with that reason; it never guesses `PASS`.

## What happens with the verdict

`PASS` lets the code canary request the merge at that exact head, when the repository's switches allow
(`jr/autonomy.json` `code_automerge`, repository variable `JR_CODE_AUTOMERGE`), at most one such merge an
hour, after every required check is green. `BLOCK` labels the PR `needs-human`; nobody waits — the author's
next push starts a new review. A person audits merged PRs after the fact and holds the kill switch.
