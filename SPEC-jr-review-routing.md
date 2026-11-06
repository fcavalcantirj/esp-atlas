# SPEC — Jr risk-based review routing (`jr-review`)

> **Status:** built 2026-11-04 (`jr/review_routing.py`, wired into `jr/publish.py` and `jr/tick.py`).

## Why

`jr/publish.py` already withholds auto-merge when a stage sets `needs_human`, but nothing told the
tick that such a PR is *supposed* to wait. `jr/tick.py`'s preflight treated **any** open tick PR older
than `STALE_PR_HOURS` (3 h) that touches non-bookkeeping files as stuck and aborted the tick — so one
PR legitimately waiting for the owner blocked every hourly tick after three hours.

## The contract

### 1. One classifier — `jr/review_routing.classify(changes, stages, needs_human=False) -> Route`

`changes` is the **staged** diff (`git diff --cached --name-status --no-renames`), each entry a path,
its status and — for a modified `data/**.md` record — the HEAD and index text. `stages` is the tick's
stage results (`needs_human`, `review`). `Route.route` is `"review"` or `"auto"`; `Route.reasons`
names every path/stage that forced review.

**REVIEW** (auto-merge withheld, PR labelled `jr-review`):
- any **new** `data/firmware/**` file (a new firmware entry), except a `signals.json` snapshot;
- any new or changed `data/recipes/**` (a compatibility claim);
- any change to the flashing fields of a `data/boards/**` record — `usb`, `usb_serial`,
  `download_mode`, `first_flash_notes`, `flash_mb`;
- any device-evidence `needs_review` item a stage reported, or any stage asking for a human;
- **anything not on the AUTO list** — when unsure, review. That includes an empty or unreadable
  staged diff, a deletion outside bookkeeping, and a record edit beyond a star/date refresh.

**AUTO** (low-risk only):
- bookkeeping: `BOOKKEEPING_FILES` (`jr/proposed_ledger.json`, `jr/board_cooldown.json`) and
  `BOOKKEEPING_DIRS` (`docs/telemetry/**`);
- snapshots: `docs/demand/**`, `data/firmware/<id>/signals.json` (added or modified);
- a GitHub star/fork/date refresh of an **existing** firmware record: only GitHub count,
  stable repository ID and observation date fields may change. Downloads, editorial home,
  their dates, all other content and the body remain identical. New or updated field-exact
  GitHub citations must name the record's repository URL and the new observation day;
  unrelated citation additions, removals or URL edits route to REVIEW. The legacy
  `field: popularity` citation may only advance its verification date with an old-style
  count refresh, never change URL or scope.

### 2. Publish applies the label — fail closed

A `review` route opens the PR, ensures the label (`gh label create jr-review … --force`, idempotent; a
failure is noted, not fatal), then `gh pr edit <url> --add-label jr-review`; if that fails, once more
through REST (`POST repos/{o}/{r}/issues/<n>/labels`). Auto-merge is **never**
requested on a `review` route. If labelling still fails, the result says so
(`labelled=False`, reason contains `jr-review label FAILED`) — auto-merge stays withheld either way.
`PublishResult` gains `route`, `review_reasons`, `labelled`.

### 3. Tick triage

- The open-PR list is read with `--limit 500` (gh defaults to 30, newest first; review PRs are the oldest).
- An open PR carrying `jr-review` is **never stuck** (never raises `TickAbort`) and **never closed as
  superseded**, whatever its age or mergeability.
- Unlabelled stale content PRs keep the old behaviour (abort, naming the PR) — including a review PR
  whose labelling failed: the abort is the fail-closed signal that it needs the owner.
- `jr/demand_run.py` never closes a `jr-review` demand PR as superseded either.
- **Cap:** `MAX_OPEN_REVIEW_PRS = 10` concurrent open `jr-review` PRs (any branch). At or above the
  cap the tick skips every review-producing stage (every content stage unless it declares
  `produces_review = False`) and reports `jr-review cap reached …` instead of piling up. Memory
  reconciliation and the telemetry snapshot still ship (they route AUTO).
  `stage_popularity_refresh.run` may opt out only because it checks each proposed record
  against this same staged-diff classifier before writing. Any change classified REVIEW is
  deferred and counted in its summary, so the stage cannot open a new review PR through the
  cap. A normal legacy snapshot plus new, exact GitHub field citations stays AUTO.

### 4. Tick report

`TickReport.review_prs` lists every open `jr-review` PR with its age; the one-line report renders
`jr-review open N: #12 30h, …`. A tick that opens a review PR notifies Telegram like `needs_human`.

### 5. Durable owner-review decisions — never re-ask an unchanged target

**The bug (2026-11-06, #1478 … #1488, #1490).** The admit stage met
`gdantas04/cardputer-system-monitor` (repo_id 831377003) every hour, the device-evidence gate said
`needs_review_target`, the `review` item routed the whole tick PR to REVIEW and the 60-day
rejection it wrote rode in that PR's ledger only. A review PR is not merged on its own, so main's
ledger kept the old `expired` record and the next tick asked again — dragging every unrelated
bookkeeping change (signals refreshes, other floor rejects, cooldowns) onto review with it.

**The contract** (`jr/review_memory.py`, `memory.record_review_decision`):

- **A review decision is a ledger record.** `status: rejected` (TTL `NO_BUILD_SIGNAL_DAYS` from
  `review.raised_at`), the gate's `reason`, and a `review` block:
  `{outcome, pr_ref, raised_at, evidence_rev, evidence}`. `outcome` is `raised` (asked in this
  tick's PR), `open` or `closed` (the owner closed that review PR unmerged). The candidate stays
  unadmitted in every case.
- **Identity** is `repo_id` (rename-proof), then `owner/repo` (lowercased), then the firmware id.
- **Evidence revision.** `evidence` keeps the raw facts — `stars`, `forks`, `downloads`,
  `editorial_home`, `source` (GitHub `pushed_at`). `evidence_rev` hashes only what is
  *meaningful*: whether stars / forks / downloads clear their floor
  (`esp_atlas_core.floor`), the editorial home, and the source revision. A star more or less is
  not new evidence; crossing a floor, a new editorial home or a new push is.
- **The PR body carries the decision.** Every review PR body ends its "Needs owner review" section
  with `<!-- jr-review-targets: [{id, repo, repo_id, evidence_rev, reason}] -->`. PRs opened before
  this marker existed are read from their rendered `` - `owner/repo` (`id`) `` lines (no revision:
  read as "unchanged").
- **Reconciliation, every tick** (tick step 3c, after the open-PR hydration): one
  `gh pr list --state all --label jr-review` (counted). For each target, the most recent PR that
  raised it decides: OPEN → `outcome open`, CLOSED unmerged → `outcome closed`, MERGED → nothing
  (its ledger already landed on main). The decision is written into the worktree ledger unless
  it already says the same, it expired (`raised_at` + TTL ≤ now), or a newer decision exists.
  Idempotent: an unchanged decision writes nothing. A failed lookup is a warning, never an abort.
- **Persistence path.** Holding the target makes the tick produce **no** `review` item for it, so
  the tick PR is routed by its files alone — bookkeeping → AUTO — and the decision-only ledger
  change lands on main through the ordinary bookkeeping path. From then on main's ledger holds it
  across ticks and restarts, whatever happens to the review PR.
- **The admit gate** reads a live review decision differently from any other rejection: it
  fetches the repo's metadata (one counted call) and compares the evidence revision. Unchanged
  (or unknown on either side) → held, counted as already decided, no review item; a missing
  revision is backfilled. Changed → reconsidered through every gate as if new (the held record is
  not its own `duplicate_of`). An expired decision is reconsidered like any expired record.
- **History.** Overwriting a review decision (or a record that already has `history`) appends the
  previous record, minus its own `history`, to `history`. Records are never deleted.
- **Nothing is weakened.** The classifier, the floor, the cap and every gate are unchanged: a new
  or changed target still opens a `jr-review` PR, and new firmware/recipes still route to review.
