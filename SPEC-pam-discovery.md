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
