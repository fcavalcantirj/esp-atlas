# PAM discovery leads

Status: adapter contract, 2026-11-06. This document is not an activation receipt.

PAM is a discovery/cross-check source. It is not an authority for Atlas catalog
facts or a license to mirror third-party content. Jr must verify each publishable
fact against a cited primary manufacturer source and retain existing review,
schema, compatibility and flash-safety gates.

## Inputs and boundaries

- GET only `https://pamfinds.com/api/products.json` and
  `https://pamfinds.com/api/specs.json`. No authentication, affiliate navigation or
  third-party instructions are involved. Fixed endpoints, socket timeout and body
  size cap; reject redirects, malformed JSON, inconsistent counts, duplicate IDs
  and mismatched product/spec ID sets.
- Join by explicit source ID. Scope ESP32/ESP8266 family hints only. A hint is not
  verified board identity; kits, revisions and companion chips still need research.
- Retain only source IDs, bounded identity hints, field names and HTTPS source
  pointers as unverified lead metadata. Do not persist spec values, descriptions,
  images, retailer/buy links or copied marketing text in the lead state/catalog.
- Source pointers are untrusted suggestions. A chip datasheet does not establish
  a board's installed flash/PSRAM or revision. The adapter never follows them.

## State and deduplication

Each feed receipt records its URL, fetched UTC timestamp, ETag, SHA-256 and byte
count. Each lead keeps its source ID/page, an identity/field-pointer fingerprint,
and exact normalized catalog label matches (`id`, `name`, `aka`/`aliases`). Never
match a board merely because the chip matches or a fuzzy sibling resembles it.
Potential label matches are not verified aliases or proof a record is complete.

Conditional requests use stored ETags. If both feeds return 304, reclassify the
last-good minimal leads against the current catalog; do not assume the catalog
stood still. If only one changes, refetch the other unconditionally before
joining. Any failed/inconsistent refresh raises before returning replacement
state, so the caller preserves the previous state and reports the failure.
The caller must atomically persist successful results under its existing worker
lock; the adapter does not mutate files or outcomes.

Only unmatched identities are emitted as potential research work. Stable work
keys use source ID plus a semantic fingerprint, never the fetch date/feed hash.
Handled keys are excluded. A refreshed identical feed cannot reopen completed
work. Changed hints may warrant new research but do not authorize another PR;
the broker must reconcile existing target work first and apply its global caps.

## Integration and acceptance

The existing daily demand runner owns fetching/persistence. The existing automatic
research consumer owns primary-source research and reviewed PR creation. Search
demand has priority over market leads; the same one-new-work-per-day and backlog
caps apply. No new cron job, monitor or scheduled paid inference is introduced.

Feed provenance is typed `pam_feed` with a fetch timestamp and feed receipts. It
has no invented GA4/GSC counts or search date window. The broker must deliberately
support this provenance type; missing search provenance must remain invalid for
actual GA4/GSC candidates. The adapter alone is not an autonomous consumer.

The broker joins validated minimal feed state into the shared policy. New search
work has priority over new market work, while any previously reserved/linked work
is recovered first. The same global daily and outstanding-work caps apply across
both source types. An exact normalized search identity suppresses a parallel feed
hint; final identity and publication still require primary-source research.

A feed work key is the adapter's opaque semantic `pam-` key (source ID plus hint
fingerprint), independent of fetch date/hash and current catalog matches. Its
reservation retains the original minimal lead, feed receipts and candidate
lifecycle snapshot. Recover that snapshot even if a later feed removes the lead,
changes its hints or now matches a newly published board. Terminal semantic keys
remain handled; a refresh never reopens them. Search candidates continue to require
their real window and source metrics; PAM records and outcomes contain neither.

Only supported, complete feed provenance permits reservation. Corrupt cache may
defer feed work but cannot block valid search work; malformed existing work
receipts still fail closed. A feed hint, `new` status or unverified boolean never
permits authoring: the same readable exact-identity/primary-source receipt and
affirmative current-head review gates apply. Delivery evidence retains the
reservation's original feed snapshot, rather than replacing it with today's hash.

Required evidence:

1. Offline tests: fixed URL/size/schema bounds, ID join, last-good failure behavior,
   304 refresh with a changed catalog, exact sibling separation, no third-party
   values in persisted state and semantic/handled-outcome deduplication.
2. A bounded real-feed read showing eligible lead counts and preserved source
   provenance, without publishing feed spec values into the catalog.
3. Reviewed integration into the existing configured jobs and their actual run
   receipts. Separate a manual invocation from the first natural scheduled run.
4. A genuine lead disposition/linked PR and, where appropriate, primary-source
   review, deployment and verified outcome. A queue entry is not completion.

The adapter's output and tests do not establish that steps 3 or 4 have happened.

## Daily runner hook

`pam_run.refresh_worktree(fresh_worktree, ...)` is the persistence boundary. It
reads board identities from that worktree using the research queue's shared
catalog loader, refreshes the two feeds, and reuses its atomic JSON writer for
`docs/demand/pam-leads.json`. It returns a changed-path manifest and bounded run
receipt. Corrupt cache, malformed catalog, feed failure or failed persistence
returns `deferred` without replacing last-good state. Timestamp-only refreshes
return `unchanged` and do not create daily metadata PRs.

The existing runner must call it inside its lock and include its changed path
even when demand is unchanged or empty. Its empty-snapshot restoration must not
discard PAM state. A deferred PAM refresh must not prevent GA/GSC work from
continuing. This helper neither publishes a PR nor changes scheduler settings.
An explicit manual probe is available with
`python3 jr/pam_run.py --worktree <fresh-worktree> --json`; the path is required
so a probe cannot accidentally target the helper's own checkout.

The configured recurring hook, publication of minimal state and an actual job run
are still required before claiming recurring consumption. The consumer must
reconcile reserved/linked work independently of today's filtered new-lead list.

The existing `scripts/jr-demand.sh` entrypoint calls `demand_run.main`, which
explicitly passes this refresh helper. A changed feed can publish PAM metadata
alone when search demand is unchanged or unavailable. No empty dated steer is
published, and a primary search failure still produces a nonzero CLI exit even
when the independent metadata publication succeeds. Ordinary PAM failure preserves
last-good state while search publication continues. Host timeout aborts remain
fatal in both the reservation and PAM paths.

The runner first reconciles/reserves committed demand and existing work. Only a
genuine policy NOOP permits a second bounded reservation pass after a changed
successful PAM refresh; caps, unreadable remote state, active work and timeouts
never trigger that fallback. A first feed reservation publishes with its changed
minimal feed metadata, including when the dated search snapshot is a no-op. Search
source failure can still publish independent feed metadata but does not start new
work from that failed pull. No new scheduler or executor is introduced by intake.

The CLI prints a bounded `PAM receipt` containing feed statuses/hashes and distinct
runner/catalog revisions. The runner executes from the scheduler's existing clone;
the miner reads a fresh main worktree. Deploy and verify the runner's revision as
well as the catalog revision. A fresh catalog alone does not activate new runner
code. A real enabled schedule/configuration and its execution receipt are required;
the tests and an isolated manual helper run are separate evidence.
