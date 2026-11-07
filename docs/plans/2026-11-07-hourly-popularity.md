# Full eligible-catalog hourly popularity: review and release plan

Owner: `codex_seo_audit_20261105` (implementation); DESIGN (independent review);
DasBrow (runtime/release). This document describes a proposed code path, not a
production sweep or merge instruction.

## Verified starting point

At immutable main `1a497be3680852b85aebb85517ba8c2a9611f0d4`, a read-only
frontmatter audit found 147 firmware records and 147 syntactically canonical,
distinct GitHub URLs. Six records have a positive `github_repo_id` and
source-specific `github_as_of`, both cited to their exact URL. The Nyan URL
currently points to an unrelated repository and remains quarantined; there
are 146 unquarantined candidates, not 146 independently verified identities.
Nyan needs a separate official, cited URL correction before it can enter this
pass. Never infer its identity from its name.

The deployed seven-repo hourly slice and 24-hour due threshold cannot deliver
full-catalog hourly attempts. The 00:00 and 01:00 natural ticks spent 122/150
and 127/150 counted GitHub calls respectively while their seven refreshed
counts remained in open `jr-review` PRs [#1503](https://github.com/fcavalcantirj/esp-atlas/pull/1503)
and [#1506](https://github.com/fcavalcantirj/esp-atlas/pull/1506). The 02:00
tick spent 132/150 calls; the runtime coordinator measured 146.3 seconds.
The coordinator's read-only GitHub quota check at ~02:12 UTC found core
4940/5000 remaining and GraphQL 4998/5000; the local service cap and review
bundling, rather than GitHub's primary quota, were the observed bottlenecks.
These numbers are a point-in-time runtime receipt, not a future quota promise.

## Proposed retrieval and publication

The existing script-only scheduler and wrapper still run once hourly, with no
model invocation. `tick.py` invokes the popularity pass before growth; both
execute under `scripts/jr-tick.sh`'s thermal check, one outer `flock` and a
600-second hard timeout. Growth retains its 150-call/360-second budget.
Popularity has a separate maximum of 12 source GraphQL HTTP requests and a
60-second source window. Each source request has an eight-second deadline;
catalog validation has a separate 60-second deadline. On the measured
146-candidate tree, one quota probe plus `ceil(146/25)=6` batches is seven
GraphQL HTTP requests. [GitHub's GraphQL rate rules](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
use point cost separately from HTTP request count; the pass records both and
reserves at least 50 points before further batches. The 60+60+360=480 second
configured windows leave 120 seconds under the wrapper for preflight,
worktrees, git, PR and other overhead. A slow operation can still hit the
wrapper timeout; no complete-coverage claim is made without natural timing.

Each alias is bound to the requested canonical owner/repo. The response must
have matching `nameWithOwner`, a positive numeric `databaseId` or matching
`fullDatabaseId`, complete nonnegative `stargazerCount` and `forkCount`, and
the same repository ID as an existing citation if present. The opaque
GraphQL node ID is never substituted. Only validated values pass the existing
floor and risk-routing checks, then receive field-exact citations and an
observation date. Failed/partial/rate-limited responses preserve last-good
counts. There is no same-run retry. 403/429 and HTTP-200 rate-limit envelopes
stop later batches; valid longer `Retry-After`/reset values or a one-hour
fallback create a box-local cooldown. The next hourly pass checks both that
cooldown and live GraphQL quota before reading repositories. Every candidate
has an attempted/failed/deferred/excluded outcome and age in the receipt.

The popularity pass uses its own fresh worktree and guarded PR. Its publisher
stages only the returned firmware popularity paths, a per-record JSON receipt
and the unchanged ledger pathspec; unrelated recipes cannot enter the commit.
If one bot-owned AUTO popularity PR remains open at the next run, the new
snapshot replaces its branch only through an exact-head force-with-lease and
verifies the same PR is still open. A review-labelled or ambiguous/multiple
pending PR blocks replacement for human resolution. A push/PR failure is
reported; the growth tick still runs. Existing branch protection, required
CI and Jr's earned-trust auto-merge rule remain in force. Fetching or opening
a PR is not a claim of committed or deployed freshness.

## Evidence and release gates

Offline tests cover the 146-candidate six-batch path, Nyan exclusion,
duplicate/budget accounting, stable ID and count failures, below-floor
deferral, partial GraphQL data, 200/403/429 rate errors with damaged bodies,
cooldown, exact-head pending PR replacement, and popularity-only pathspec.
Catalog validation is required. The macOS local full Jr suite has unrelated
fixture constraints (local HTTPS and Linux `bwrap`/preexec tests); required
Linux CI is the authoritative gate for those. No paid inference test is run.

After exact-head DESIGN/planner review and green required checks, DasBrow owns
merge and runtime rollout. The first natural run receipt must name scheduler
run ID, source revision, all eligible/attempted/success/failure/deferred counts,
GraphQL HTTP requests, point cost/remaining, all GitHub publication calls,
elapsed time, PR head and whether auto-merge armed. The release receipt must
then show the merged main revision, completed Vercel deployment, revalidation
result and live `/api/firmware/{id}` source dates for sampled records. Report
each excluded or failed record by ID; do not call a count fresh because the
job ran. If CI or deployment exceeds the hour, or a PR remains open, report
the actual delay and investigate before claiming hourly visible freshness.
