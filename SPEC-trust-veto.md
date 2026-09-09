# SPEC: trust veto — a close resets earned auto-merge only when it is LABELLED

## The rule

`jr/publish.py::trust_status` decides whether Jr has earned **auto-merge** for its tick PRs.
Jr earns it when its last `N = TRUST_N = 10` *terminal* PRs (ignoring benign closes) were all
**merged** by a human. A **veto** resets the count — but a close counts as a veto **only when the
closed-unmerged PR carries a label in `VETO_LABELS = {"veto"}`** (matched by name,
case-insensitive).

A closed-unmerged PR **without** a veto label is **benign** — a superseded / duplicate /
housekeeping close. It is excluded from the calculation entirely: it is neither a merge nor a
veto, and it does **not** reset trust.

Fetch semantics: the recent closed PRs are fetched with their labels, over a wider window
(`fetch_limit = max(N*3, 30)`), because benign closes are filtered out and up to `N` non-benign
PRs must still be found. PRs are classified in recency order, benign closes are dropped, and the
first `N` of the remainder form the window. Any veto in the window → reset; else fewer than `N`
merges → "trust not yet earned"; else → earned.

## Why (the death spiral)

The old code treated *any* closed-unmerged PR as a veto. It could not tell a **human veto of bad
work** from a **housekeeping close of a redundant/duplicate tick PR**. That produced a self-
reinforcing failure:

> one incident → a few closes → trust reset → auto-merge off → PRs pile up → the pile-up breeds
> duplicate/superseded tick PRs → clearing those duplicates forces MORE closes → trust never
> re-earns.

Making a veto require an explicit label breaks the loop: routine cleanup of duplicate tick PRs is
benign and cannot, by itself, hold auto-merge off forever.

## CI vs. trust — two different gates

- **CI is the quality gate.** Branch protection requires `schema`, `tests`, `jr-tests`; a red-CI
  PR cannot merge regardless of trust. Quality is never the trust gate's job.
- **Trust is the human-veto gate.** It encodes human *judgement* — "this work is wrong, reject
  it" — not code quality. So only a deliberate, labelled human action should count against it.

## Operator procedure

- **To reject Jr's work and reset earned auto-merge:** close the PR **with the `veto` label**.
  This is the one action that resets the trust count.
- **Routine / duplicate / superseded closes need no label.** Closing a redundant tick PR without
  the `veto` label is benign by design and leaves earned auto-merge intact.
