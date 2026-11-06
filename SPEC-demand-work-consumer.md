# Search demand to reviewed work — implementation contract

Status: implementation contract, 2026-11-06; not an activation receipt. This owns
the broker, automatic execution handoff and outcome verification. It extends the
existing demand/research specs without adding a new cron or changing risk routing.

This extends `SPEC-demand-research-queue.md` and `SPEC-jr-demand-driven.md`.
The miner remains read-only with respect to `data/`. A separate consumer uses an
existing execution cadence; it does not introduce another scheduled job or an
inference availability monitor. Implementation is not activation.

## Required execution path

1. The existing daily demand runner reserves work after mining; the existing daily
   checkup agent executes the reservation automatically. These are the selected
   runtime hooks, subject to verified integration and the configured prompt. The
   broker reads the latest committed queue and reconciles
   previously linked work before selecting anything new. Its actual job ID,
   command/prompt, cadence, code revision and run receipt must be recorded locally
   without credentials, recipient tokens or maintainer host paths in public docs.
2. It automatically selects one eligible candidate, researches the exact identity
   against primary sources, and either creates one concrete reviewed/draft PR or
   records a supported deferred/rejected result. It must not depend on a person
   noticing a demand PR. Creating a ticket without a configured executor does not
   satisfy this path.
3. Risky catalog, firmware, compatibility and flashing changes retain existing
   review routing, source-or-omit, required CI and withheld auto-merge behavior.
   Source claims remain `unverified` unless the existing evidence gates permit more.
4. After a linked PR merges, the worker verifies the intended deployed result.
   Only then can it persist a delivered outcome and close the candidate. A merge,
   an HTTP 200, a broad fuzzy hit or a newly created queue entry is insufficient.

## Selection, budget and identity

- Intake includes GA4 zero-result research candidates and eligible GSC UNRESOLVED
  demand items. GSC impressions/clicks/position remain GSC metrics; do not invent
  GA4 submit/empty counts. Preserve the source snapshot, exact signal window and
  source-specific metrics in each work receipt. Overlapping windows are not totals.
  PAM potential identity gaps join as typed `pam_feed` research work under
  `SPEC-pam-discovery.md`; they retain original minimal feed provenance without a
  fabricated search window or metrics. Existing work is recovered before any new
  work, and new search demand has priority over market leads under the same caps.

- Initial hard cap: one newly started work item per UTC day, one item per run and
  one outstanding catalog-authoring work item. Reconciliation is allowed at the
  cap. An interrupted/retried item consumes the same slot, not another one.
- Candidate key: normalized term plus its current lifecycle opening date, so a
  permitted future reopening is distinguishable from a retry. Derive a stable
  opaque work ID and deterministic branch name from that key. Never derive shell
  commands, URLs or paths by interpreting raw search text as instructions.
- Recover the lifecycle date from committed candidate state or an existing remote
  work marker. A crash before the initial queue publication must not cause a new
  calendar date or a sliding source window to generate a second work identity.
- Read candidate status, source, original signal window and prior work references
  from committed state. Preserve them in the work receipt and PR description.
- `new` permits research only. `validated` permits authoring only with a readable
  identity/primary-source receipt; a bare status flag is not proof of a board.
  `linked` resumes/reconciles its work; `closed` is skipped until the existing
  reopening rule actually creates a new lifecycle.
- Distinct physical SKUs stay distinct, including ES3C28P/ES3N28P and FNK0104S/A/B.
  A shared family token, sibling datasheet or generic chip match is insufficient.
- Unsupported identity, ambiguous interpretation, inaccessible primary evidence,
  a full review backlog or unavailable APIs defer without guessed catalog facts.
- The separate agent may propose a reviewed intake/resolver code repair for a
  search-defect candidate. This does not add a model to deterministic answer paths
  or let the hourly script silently change its own gates.

## Idempotence and failure recovery

- Use the existing single-writer lock, or a lock shared by all invocations of the
  consumer. Document its scope; do not claim global exactly-once behavior from a
  host-local lock.
- Before creating work, reconcile deterministic branches and PRs/issues in all
  states, including closed and merged ones. An unreadable/truncated listing is
  not an empty listing and permits no blind create.
- Persist/recover the daily reservation and work ID. A crash after a remote create
  but before a local save must recover that same remote work by ID/branch rather
  than create another PR. An uncertain write response triggers readback before
  another attempt. Queue/state writes remain atomic and preserve the previous
  valid file on failure.
- The daily producer's first pass may recover an existing PAM branch/open PR from
  validated cached provenance, even if fresh search demand is eligible or a feed
  refresh fails. New PAM work still requires a successful current-catalog feed
  refresh; cached classification alone never opens a new work item.
- Never overwrite a newer queue, another candidate's state, human review decision,
  linked work or previously recorded outcome while publishing bookkeeping.

## Outcome evidence

- Record the linked PR URL and merge SHA, expected catalog IDs/query behavior,
  deployment revision, verification timestamp and actual response IDs/status.
- `delivered` requires a merged reviewed change and its specific live postcondition.
  A sibling result or missing expected ID leaves the candidate linked/deferred.
  The validation receipt may list `forbidden_ids` (sibling SKUs it ruled out, disjoint
  from `expected_ids`); a live result returning any of them alongside the expected set,
  or returning only part of that set, is not delivery.
- Closure evidence carries the reservation's original source/window/metrics, never the
  queue's later refreshed sliding window.
- Exact-model catalog work requires the complete declared expected-ID set, without
  additional sibling/unknown results. Order is irrelevant. An explicit forbidden
  ID cannot also be accepted as an expected target; malformed IDs remain pending.
- Closed-unmerged work is explicitly rejected/abandoned, with its reason; it is
  never labelled delivered. Unreadable merge/deployment/search state is deferred.
- Preserve original GA4 source/window/counts and historical classification evidence.
  Do not generate fake production searches or analytics events to demonstrate flow.

### Verification must match the actual defect

The validation receipt declares a verification kind. For missing catalog content,
verify exact public search/catalog IDs at a deployment containing the merge. For a
miner-resolver repair, verify a fresh successful miner run at code containing the
merge, its resolved target and expected classification. The receipt must name the
same merge and be observed on the current UTC day; HTTP success alone is insufficient.

The first genuine candidate identified is GSC `fnk0104s`, snapshot 2026-11-05,
window 2026-10-08..2026-11-05: 22 impressions, 1 click, position 8.2, UNRESOLVED.
Public search already returns `freenove-fnk0104s`. Its new work is therefore a
MINER resolution defect, not a missing board or a broken public search. Completion
requires a new actual miner result resolving that exact board with a covered gap,
while FNK0104A/B remain distinct. Existing controller work must be reconciled before
creating a duplicate. Adopting existing work must be reported as adoption, not a new
autonomously authored PR.

## Required acceptance cases

1. Closed ES3C28P on current main: actual worker run is a no-op, zero new work.
2. New candidate: the configured worker performs source research automatically;
   no catalog write before identity validation. A ticket-only path fails acceptance.
3. Validated exact-model candidate: one specific draft/review PR and persisted link.
4. Same-day rerun, concurrent invocation, crash-after-create and unknown response:
   one work ID/branch/PR, recovered state, no duplicate and no extra budget slot.
5. Daily cap/backlog cap/API outage: no new work; existing work still reconciles.
6. Unreviewed risky change, sibling SKU or unsupported source: no auto-merge or
   verified/flashable promotion.
7. Merged PR plus stale/wrong live response: candidate stays open.
8. Merged PR plus exact live postcondition: outcome and closure persist on main,
   with original provenance and a readable verification receipt.
9. Report controlled fixture results, configured activation, an actual no-op run,
   and the first genuine production candidate outcome as separate evidence tiers.

The broker/runtime implementation, configured existing worker and first genuine
end-to-end receipt remain required. This contract and its offline oracles alone
must not be described as a deployed or self-growing system.
