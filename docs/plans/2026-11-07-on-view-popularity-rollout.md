# On-view popularity rollout gates (2026-11-07)

Owner: backend `codex_seo_audit_20261105`; frontend DESIGN. This is a review plan,
not authorization to provision storage or turn on live GitHub calls.

## Current decision and lean options

The existing git-tracked firmware frontmatter is already the durable catalog for
the page's cited counts. The deployed hourly Jr job is script-only and invokes
no LLM. Each run selects at most seven distinct repositories; the 24-hour due
threshold and rotating slots aim for a daily pass when runs succeed. A count can
be older after a skipped run, failed lookup, floor/provenance deferral, or delayed
deploy. The page already displays the individual GitHub source date, including
historical snapshots. **Hourly execution is not a one-hour freshness guarantee.**

There are two concrete user-visible choices:

| Choice | What a page view shows | Additional shared resource | Trade-off |
| --- | --- | --- | --- |
| Existing catalog only | Last committed cited counts and their source date | None | Leanest operating path; a view cannot cause a fresh GitHub lookup. |
| Catalog plus optional on-view overlay (this PR) | The same cited fallback, plus a newer verified GitHub count when eligible and available | One read-write shared coordinator | A view can refresh an eligible repo, subject to the global budget, cache and cooldown; requires resource, migration and deployment approval. |

The earlier on-view request remains in scope. Felipe's later condition permits
the hourly no-LLM job but does not withdraw that request or authorize storage.
Keep this PR draft and the endpoint disabled until the resource and release gates
below are decided. A static JSON export of the catalog can help a client read
data, but a Vercel function's local JSON file is not shared durable storage for
cross-instance leases or an atomic hourly reservation. The regional Runtime
Cache likewise cannot be the sole global coordinator. The current Postgres
implementation is the smallest reviewed shared coordinator for the stated
20-per-hour hard cap and single-fetch deduplication; no esp-atlas database
resource exists yet.

## Wire and failure contract for frontend preparation

`GET /api/firmware/{id}/popularity/live` returns `Cache-Control: no-store` and
`firmware_id`, `outcome` (`fresh`, `cached`, `stale`, `unavailable`, `ineligible`),
`catalog` (`stars`, `forks`, `github_as_of`, `source_url`, `repo_id`), nullable
`github` (`stars`, `forks`, `observed_at`, `source_url`, `repo_id`), and nullable
`retry_after_seconds`. Catalog fields may be null when the source has no cited
value; zero counts are real values. The UI may use `github` only when non-null;
the backend exposes it only when its observation is newer than the catalog's
GitHub date and its stable repository ID and full name match the canonical
record. The UI always keeps the cited catalog and source date as fallback.

With `POPULARITY_DATABASE_URL` unset, an eligible record returns
`outcome: unavailable`, `github: null`, and makes **zero** GitHub calls.
An uncited/invalid ID, date or non-bare GitHub URL returns `ineligible` and also
makes zero calls. A store outage returns the catalog without a GitHub call.
After a successful store claim, a GitHub timeout, invalid payload, exhausted
budget or cooldown uses a newer last-good eligible overlay when available,
otherwise the catalog; neither failure path fabricates zero counts or edits
catalog files.
Frontend fixtures and parser tests can be prepared against this fixed shape
without activating a live request in production.

## Request budget and local evidence

The on-view coordinator reserves at most **20 GitHub requests per UTC hour**
across all page instances, before network I/O. It has one global and one
per-repository lease, so concurrent cold views of the same repo coalesce to
one fetch. A valid overlay is cached for one hour and retained for up to seven
days as last-good fallback. Each claim makes at most one GitHub request with a
five-second total deadline and no same-view retry. A 403/429 applies global
cooldown, even if its body cannot be read; other failures back off the repo.
The separate hourly Jr stage has an at-most-seven-repo ceiling per tick, so
these two popularity paths together can attempt at most 27 repository lookups
in one hour when both are enabled. This is a cap on this application's calls,
not a promise about GitHub's rate-limit allowance or whole-catalog freshness.

The repaired backend code at `30a85b2834e4e9378daaaaab593aa70a326ecc15`
has local evidence: 162 offline API tests passed; 48 focused tests passed with
a disposable Postgres primary, including 12 real-SQL cases for contention,
lease expiry, hour boundary, identity fencing and damaged 403/429 responses;
catalog validation passed 611/611. The disposable database was stopped. These
are draft-code tests, not production on-view proof. CI, current-head review,
the approved store, source-ID coverage, frontend integration and a natural
page-triggered production receipt remain separate gates.

## Repository ID coverage

At immutable main `97f7b6a4d09b976182ded3fc1ff9efc3e24c2f4f`, a read-only
frontmatter audit found 147 firmware records with bare GitHub URLs and 6 records
eligible for the on-view endpoint: `cardputer-microhydra`,
`claude-desktop-buddy-cardputer`, `evil-portal-m5stack`,
`m5-clicker-hamster`, `nerdminer-v2`, and `nucleoos`. The other 141 lack a cited
positive `popularity.github_repo_id` and source-specific `github_as_of`. One of
those, `nyan`, is quarantined by `jr/stage_popularity_refresh.py` because its
current URL identifies a different project. There are 146 distinct unquarantined
repository URLs; 140 are not yet eligible. These are measurements of that exact
tree, not promises about later main.

Use the **existing hourly Jr popularity refresh** to fill the gap. It selects
at most seven distinct repositories per hour under Jr's counted GitHub-call and
wall-clock budget. For each selected record, it accepts only a GitHub API 200
whose `full_name` matches the recorded owner/repo and whose positive stable `id`
agrees with any stored ID. It requires complete nonnegative star/fork counts,
preserves launcher/home signals, and writes field-exact citations plus
`github_as_of`. The stage's review routing, floor check and Nyan quarantine
remain in force. Do not copy IDs from Jr's ledger, infer IDs from URLs, or
run an unbounded one-shot sweep to make the UI appear complete.

With 146 unquarantined distinct repositories and 24 hourly slots, a complete
successful cycle can attempt every unquarantined repo once in 24 ticks. Skipped
calls, failed identity checks, review-cap deferrals and below-floor results
remain ineligible and are reported individually. After every natural tick,
audit committed main for: (a) `github_repo_id` positive and cited to that
record's exact source URL, (b) `github_as_of` cited, (c) full name matching,
(d) `scripts/validate.py` green, and (e) a deployed `/api/firmware/{id}` readback.
The first coverage target is **146/147**, conditional on successful reviews and
ticks. `nyan` needs its own cited URL correction and identity review before a
147/147 target is honest. If coverage stalls after a full cycle, report each
record and cause; do not silently broaden eligibility.

## Database and migration

Read-only Vercel inventory on 2026-11-07 (`vc integration list --all`) found Neon
resources assigned to other projects and **none assigned to esp-atlas**. Use a
dedicated read-write Neon Postgres primary for this feature; do not reuse an
unrelated project's resource. The Vercel Marketplace offers Neon integration,
but its exact plan, billing, project binding and credential mapping require
Felipe's confirmation before provisioning. No storage has been provisioned,
and no credential has been read or injected for this feature.

1. Merge backend PR only after DESIGN/planner review and required CI. Keep
   `POPULARITY_DATABASE_URL` unset; endpoint returns cited catalog with
   `outcome: unavailable`, and makes no GitHub request.
2. With Felipe's resource/plan approval, provision a dedicated Neon resource
   for the esp-atlas Vercel project. Bind its **primary** connection to the
   server-only `POPULARITY_DATABASE_URL`; never bind a read replica or expose
   the URL through `NEXT_PUBLIC_*`. Isolate preview tests from production data.
3. Apply `migrations/20261106_live_popularity.sql` to that primary once, in a
   transaction. Confirm its singleton row exists, starts at zero reservations,
   and both tables have their constraints. Record migration time and database
   branch/resource ID in the deployment receipt without recording credentials.
4. Enable the environment variable only after migration. Deploy, then check an
   eligible record's detail-triggered request: source URL, repo ID, observed
   timestamp, counts and `fresh`/`cached` state must be consistent. Two
   concurrent requests for the same uncached ID must consume one reservation
   and at most one GitHub fetch. Query the budget and repo rows on the primary
   for the receipt; confirm `used <= 20` in the UTC hour and no lingering lease.
5. DESIGN wires one client request after detail hydration, with cited catalog
   fallback and source/date display. Verify mobile/desktop navigation and
   no direct browser-to-GitHub call. Natural on-view production proof requires
   an actual page visit, not a synthetic API call alone.
6. Rollback is to unset `POPULARITY_DATABASE_URL` and redeploy. The API then
   remains readable with catalog fallback and cannot call GitHub. Preserve
   the database for review rather than deleting it during incident response.

Release stays open until the approved store, source-validated ID coverage,
frontend integration and real page-triggered proof have all been reviewed.
