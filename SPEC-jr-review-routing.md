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

- **Jr's own retraction (owner, 2026-11-11).** A recipe deletion is AUTO only when the same diff adds
  `jr/overrides/<firmware>__edges.json` with `directed_by: jr-self-correction`, a known classification,
  and `deletes` and `originals` naming exactly those deleted recipes of that firmware, at most
  `MAX_SELF_CORRECTIONS` per tick. Any other recipe or firmware deletion stays REVIEW or refused.
  `scripts/g2_guard.py` still verifies the override byte for byte in CI. Details:
  `SPEC-firmware-board-mapping.md` section 4.1.

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
  GitHub count refresh is no longer a tick stage: the independent runtime JSON publisher
  updates counts without catalog PRs. The cap does not block that publisher. Stale content
  PRs retain the human-review rule above, including historical count-refresh PRs.

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

### 6. Pending and vetoed proposals — never re-stage what a Jr PR already holds

**Incident (main ce0f72af).** Open jr-review tick PRs #1500 #1501 #1503 #1506 #1508 #1511 each
re-added the same nightdriverstrip recipes + signals (and squachwatch-cyd's). Those firmware were
already catalogued, so their ledger record is `merged`; the open-PR hydration's `proposed` write is
refused over a merged record, so boardmap's "already proposed" skip never fired and every hourly
tick re-derived the firmware into another review PR. A veto of a PR whose proposal never reached
main was forgotten the same way.

**The contract** (`jr/pending_prs.py`, tick preflight):

- **Source of truth: the PR's own changed-file list**, read-only from GitHub — never a ledger
  status. A firmware id is held when a `jr/tick-*` PR changes `data/firmware/<id>/…` or
  `data/recipes/<board>__<id>/…`.
- **Open → held** (`already_proposed`) for as long as the PR is open. The preflight's
  `gh pr list --state open` carries `files`; no extra call.
- **Closed unmerged → vetoed** for `VETO_TTL_DAYS` = 30 from `closedAt` (the tick PR body's
  "Close = veto … not again for 30 days"). One counted
  `gh pr list --state closed --search "is:unmerged closed:>=<now-30d>" --json …,files`; dates,
  branch and `mergedAt` are re-checked client-side. An open PR wins over an older veto.
- **Merged → nothing held**: the firmware is catalogued on main and the ledger reconciles it.
- **Unreadable → the tick aborts** before the worktree (fail closed, like every preflight query).
- **Incomplete → the tick aborts too**, naming the gap: an index that may miss a hold is as blind
  as an unreadable one, so no content stage runs and nothing is published (no admit, topics,
  boardmap, recipe or popularity write). Incomplete means any of: the open list returned
  `OPEN_PR_LIMIT` PRs, the closed list returned `CLOSED_PR_LIMIT` PRs (both may be cut), or a held
  tick PR's file list cannot be shown whole. `gh pr list --json files` carries at most the first
  100 files of a PR, so both lists also ask for `changedFiles`; a tick PR whose `files` count is
  not its `changedFiles` is re-read with `gh api repos/<slug>/pulls/<n>/files?per_page=100
  --paginate` and must then match `changedFiles` exactly (that REST listing stops at 3000 files).
- **Every staging stage obeys it.** `stage_admit` and `stage_admit_topics` skip a held id (derived
  from the repo url exactly as the scorer authors it) before any metadata fetch; `stage_boardmap`
  maps no held firmware — no recipe on the same boards and none on a NEW board (no stacking onto
  an unmerged firmware) — and gives the slot to the next candidate. `--track B --firmware` obeys it
  too. Skips are counted `already_proposed` / `vetoed` and named with the PR in the stage summary.
- **Identity is the repository, not its name.** An upstream rename turns `oldtool` into `newtool`;
  GitHub's numeric repository id stays. Every tick PR body carries a hidden
  `<!-- jr-identity: [{"id", "repo", "repo_id"}] -->` marker — the id admission read from GitHub
  for each firmware it proposes (`stage_admit` and `stage_admit_topics`). Both PR lists also ask
  for `body` and `headRefOid`. A hold keeps its verified id and its slug as the alias it was
  proposed under.
  - **The marker is never trusted alone; the committed ledger decides.** A PR body is editable by
    anyone who can edit the PR, so the marker only claims. When a tick PR changes
    `jr/proposed_ledger.json`, the ledger committed at its head is read once:
    `gh api -H "Accept: application/vnd.github.raw+json"
    repos/<slug>/contents/jr/proposed_ledger.json?ref=<headRefOid>` (`RAW_MEDIA`), and each held
    firmware takes the `repo_id` of its record there — and only that. A marker id the ledger
    contradicts is ignored (a forged `4242 → 7777` keeps 4242 held and never holds or vetoes
    7777); one the ledger does not record verifies nothing (the hold stays matched by slug). A
    marker that agrees still covers the rename. A PR without a marker (one older than it, like
    growth PRs #1511/#1513) is verified the same way, else matched by slug. A PR that does not
    change the ledger is not read: its ids stay unknown.
  - **An ambiguous marker fails closed.** On a tick PR that holds a firmware, a body that opens
    `jr-identity` more than once (a forged, duplicate or unclosed marker), whose marker is
    unreadable, or that names one firmware twice is a gap (a PR that holds nothing decides nothing): the index is incomplete and the tick aborts before its worktree — nothing is
    written to the ledger or memory. So is an unreadable ledger (or one with no head oid to read it
    at). The renderer escapes `<` inside the marker and defangs any `jr-identity` opening in item
    text and stage summaries, so a body Jr wrote opens the marker exactly once.
  Admission matches the fetched id **before** the slug:
  - same id under a new slug → held as the original (`already_proposed` / `vetoed`), named with
    both slugs, the id and the PR (rename provenance);
  - the held slug under **another** id → `identity_ambiguous`: never admitted, nothing written to
    the ledger (not a decision — not even a search-resolved launcher entry's `resolved:` note), named with both ids and the PR, re-checked every tick until the
    hold ends; a submission issue is left open and unanswered (`deferred, identity_ambiguous` in
    the summary), so it is read again once the hold ends;
  - a slug collision where either id is unknown (a PR older than the marker, an unreadable
    candidate) → held, fail closed. A hold without a verified id is still skipped before the
    metadata fetch; one with an id costs that one fetch to decide.
  - name similarity is never identity. The open-PR ledger hydration also records the verified
    `repo_id` — only the one verified for that same PR — so the ledger's own `by_repo_id` gate agrees.
- **Nothing persisted, nothing weakened.** The index is rebuilt every tick, so a merge or a lapsed
  veto releases the firmware on its own. Hydration, review decisions (§5), the classifier, the
  device-evidence gate, the `jr-review` label and the open-review cap are unchanged.
