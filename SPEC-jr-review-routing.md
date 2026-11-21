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
- **Incomplete → the tick is degraded** (2026-11-18; it aborted until then), naming the gap: an index
  that may miss a hold is as blind as an unreadable one for anything that touches firmware, so no
  stage runs unless it is declared `firmware_free` (today only board backfill, which writes
  `data/boards` and never reads a hold), and nothing is copied out of open PRs (no open-PR hydration,
  no decision carry: their committed content is what failed to verify). No admit, topics, boardmap,
  recipe or popularity write happens. Reconciliation from main, telemetry and the backfill still run
  and publish. Measured cost of the old rule: one firmware's gap in #1839 stopped every lane for four
  hours. The degraded reason goes to the abort watch (`SPEC-jr-self-heal.md` §1c). Incomplete means any of: the open list returned
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
  - **The ledger id binds only to the held firmware.md's own source** (R2i): the `firmware.md`
    committed at the same head names a repository, and GitHub must answer that repository with the
    ledger's `repo_id`; otherwise it is a gap. **Exception, a record the PR never wrote**
    (2026-11-18): the ledger at #1839's head still carried a September record under the reused id
    `wled` for a rejected fork (`toshihiromakuuchi/wled`, 846066903, `expired`), while the held
    `data/firmware/wled/firmware.md` names `wled/WLED` (76990209); four hourly ticks aborted. A
    record that fails the binding but is byte-identical in the ledger at the PR's merge base with
    its base branch (`gh api repos/<slug>/compare/<base>...<head>` → `merge_base_commit`), for a
    firmware whose `firmware.md` source at the merge base is the same as at the head, is history, not
    this PR's claim: the hold takes the id GitHub answers for that source. A record or a source the PR
    changed keeps the strict rule (no commit on the PR chooses the identity); an unreadable merge
    base, base ledger or source stays a gap.
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

### 7. Autoreview: an independent evidence check of every jr-review edge (shadow first, 2026-11-15)

**Why.** Every new firmware and recipe routes `jr-review` and waits for a person or agent reviewer.
Over 14 days (Nov 1–14) that was 53 tick PRs, median wait 8.5 h (p90 17 h, max 74 h), and the
cap of 10 open review PRs stops admission. Review is not optional, though: in the same window it
caught recipes whose cited evidence named a sibling variant (the "Cardputer ADV" firmware filed
under the original Cardputer; a Plus2 env read as a StickC), a carrier-module id under a product
build, and a category keyword matched inside another word. One of those was missed by both
reviewers. Autonomy therefore means a stronger, mechanical review, not skipping review.

**The checker (`jr/autoreview.py`).** Pure, deterministic, offline-testable. For one recipe edge
`<board>__<firmware>` and the text of the source it cites (fetched at a pinned commit where the
URL allows), it returns `PASS`, `FAIL` or `UNCERTAIN` with reasons. It has its **own** rules and
tables; it never calls `jr/device_map`, `jr/board_alias` or the admit scorer, so it cannot repeat
the mapping mistake it is checking for. The rules, each one tested on the real cases above:
- **named:** the source names the claimed board itself (its catalog name or an alias in the
  checker's table), as text, not only through a URL or a generated note. Not named → `FAIL`. A name
  followed by a library or SDK word ("M5Cardputer Arduino library", "… SDK", "… component") is a
  software reference, not the device (rules v3, 2026-11-16: an ADV-only README's library link had
  PASSed the original Cardputer in tick #1747, and the gate's reverse-sibling step wrote that edge).
  A parenthetical attached directly to the sibling's name that adds nothing with a conjunction
  ("Cardputer-ADV (Cardputer v1.1)") glosses the sibling; it is not a mention of the original (rules v4,
  2026-11-19: m5-crystal builds only `[env:cardputer-adv]` and v3 PASSed `m5cardputer` on that gloss in
  tick #1828). "(and the original Cardputer)" / "(also Cardputer v1.1)" still add it.
- **sibling:** the source names a more specific sibling of the claimed board (Cardputer **ADV**
  for `m5cardputer`, Stick**C Plus2** for a StickC, a product built on a carrier module) and never
  the claimed board on its own → `FAIL`.
- **negation:** a mention of the claimed board in a sentence that says it is not supported → `UNCERTAIN`.
- **carrier:** the claimed board is a carrier module (`m5stamp-s3`) and the evidence is a build
  environment or library that names a product built on it → `FAIL`.
- **unreadable:** no source, an unpinned or unreachable source, or an evidence class the checker
  does not know → `UNCERTAIN`. Never a guess.

A `PASS` says only that the cited upstream text targets the claimed board. The recipe stays
`unverified` (not hardware-tested), and a PR passes only if **every** claim it adds passes.

**Step 1: the gate inside generation (owner, 2026-11-15: "algorithm must clearly improve").** The same
check runs **before** Jr writes an edge, at both write points: the admit stage's first recipe (the board
picked from the repo's name or description; submissions and build-file signals keep their own evidence)
and boardmap's `writers.plan_recipes`. The evidence is what Jr already read (description, the
`platformio.ini` derive fetched, release asset names) plus one counted README read per candidate.
- `FAIL` → the edge is not written (admit records `evidence_check: <reason>`; boardmap lists it refused).
- "Cardputer" named only generically beside an ADV-only source, where the Cardputer-Adv passes → the
  Cardputer-Adv edge is written instead (`writers.evidence_gate`).
- An edge found only for the Cardputer-Adv whose source also names the original explicitly → both edges
  (`writers.reverse_siblings`).
- Every written edge carries its receipt in the recipe notes: `Evidence check v<N> <PASS|UNCERTAIN> — <reason>`.

Measured with `jr/autoreview_replay.py` (Jr's real admit + boardmap code, replayed offline on recorded
GitHub answers; `jr/fixtures/autoreview/replay-metrics.json`):

| | without the gate | with the gate (rules v3) |
|---|---|---|
| known-wrong edges written | 8 / 44 | **0 / 44** (rules v2: 1, written as PASS) |
| known-correct edges found | 18 / 24 | **21 / 24** |
| Cardputer-Adv edges for the 22 ADV-only firmware | 9 / 22 | **16 / 22** |
| written edges that PASS (auto-merge eligible) | 88.5 % | **100 %** |

**Shadow, then canary.** Phase 1 runs the checker and reports; it never merges. It is replayed on
the labelled history: every wrong edge preserved in `jr/overrides/*__edges.json` (42 at the time
of writing) must come out `FAIL` or `UNCERTAIN`, and the edges both blind audits of 2026-11-15
agreed are correct must come out `PASS` or `UNCERTAIN`. A false `PASS` on a known-wrong edge blocks
phase 2.

**Phase 2: the tick canary (2026-11-17).** Two CI jobs on every `jr/tick-*` pull request:
- `receipt-guard` (`scripts/receipt_guard.py`): eligible on receipts alone when every recipe the PR ADDS
  carries a `PASS` receipt (E1) that holds AGAIN when the checker is re-run here on the live upstream —
  the firmware repo's description, README, root `platformio.ini`, release asset names (E2); the PR edits no
  existing record and deletes nothing under `data/` (E3); it adds at least one recipe (E4). A stale or
  misstated receipt cannot merge. An upstream that does not answer is no verdict (exit 2).
- `tick-canary` (`scripts/tick_canary.py`, needs schema, tests, jr-tests, receipt-guard, jr-pr-guard,
  g2-guard, ledger-guard): when `jr/autonomy.json` has `tick_automerge: true` (a reviewed PR) AND the
  repository variable `JR_TICK_AUTOMERGE` is not `0` (the kill switch), the PR carries `jr-review`, no
  fewer than `DAILY_CAP` review-routed tick PRs merged today (UTC; **one a day** until 2026-11-21, **four**
  since: Jr opened about 3.3 a day and one a day let the queue grow until the tick yielded nothing for 24
  ticks; the first three canary merges were audited correct), and the receipt guard says eligible, it
  requests `gh pr merge --auto --match-head-commit <head>`: the merge lands only when every required check
  is green at exactly that head. The routing itself does not change: the PR is still labelled `jr-review`
  and the review cap still holds; the canary is the reader. A PR the guard refuses (an edit to an existing
  record, an UNCERTAIN receipt, a receipt the live upstream no longer supports) waits for the agent
  reviewer or a person. A person audits the first five canary merges after the fact and holds the switch.
- **Every recipe Jr writes carries its receipt (2026-11-21).** The topic stage's drain
  (`jr/drain.author_selected`) wrote "the repo lists X as a supported device" with no evidence check, so the
  receipt guard refused all of them (E1) and Jr closed four tick PRs after 72 h. The drain now runs the
  guard's own live check (`drain.live_evidence_gate`: `scripts/receipt_guard.live_sources` through
  `writers.evidence_gate`, the gate `stage_admit` runs). FAIL is never written; a sibling of the same chip
  replaces the board; PASS and UNCERTAIN are written with "Evidence check v… <verdict> — <why>" in the notes.
  An upstream that cannot be read writes the recipe as before, with no receipt, for a reviewer. Run live on
  the four stuck recipes: esp32-template, fennek and pisces-moon-os on the T-Deck PASS; xmas-tree on the
  QT Py S2 FAILS (the source never names that board) and would not have been proposed.

### 7b. Code pull requests: the agent reviewer and the code canary (2026-11-17, lanes 2026-11-18)

Every other pull request — Jr's code, the operators' code — used to wait for a person's exact-head
review (43 merges a week). `docs/REVIEW-CONTRACT.md` writes that review down. **Two lanes run it, the owner's
rule "subscription and api as fallback":**

- **Subscription lane (primary).** `jr/agent_review.py once`, an hourly job on the runner, calls the same
  coding delegate the demand executor and the CI heal use (Claude subscription, no API key, read-only:
  `--no-ship --no-merge`) on the next open code PR whose current head has no verdict (a PR already reviewed at an earlier head
  first, then the oldest update), in a detached
  worktree at that head, with `docs/ops/REVIEW-PROMPT.md` as the task. The agent writes the structured
  verdict `{verdict: PASS|BLOCK, head, findings, checked}` to a file outside the repo; the runner posts it as
  ONE PR comment beginning with `<!-- agent-review verdict -->` (lane `subscription`). Not for `jr/tick-*`,
  `jr/research-*`, `jr/heal-*` or drafts.
- **API lane (fallback).** Only when the delegate's own answer says the lane is DOWN (no
  `CLAUDE_CODE_OAUTH_TOKEN`, usage limit, 401/403/429), the runner labels that PR `review-fallback` — at most
  `FALLBACK_PER_DAY` (3) a UTC day, counted in the runner's state — and `.github/workflows/agent-review.yml`
  (trigger: that label) runs the Claude Code CLI directly (`claude -p`, an exact version; never
  `anthropics/claude-code-action`, which Anthropic bills as Claude Code, a product the plan's monthly API
  credit does not pay for: 2026-11-20) with `ANTHROPIC_API_KEY`, tools limited to
  `gh pr diff`, `gh pr view`, reading the checkout and running the touched test files, then posts the same
  comment (lane `api`) and removes the label. BUSY (the delegate's lock is held) is not down: the PR waits an
  hour. Without the secret the fallback job says so and the PR waits for the subscription lane.
- **The code canary** (`scripts/code_canary.py`, workflow trigger: a marker comment on a PR) reads the newest
  verdict comment naming the PR's current head, whichever lane wrote it, then: C1 `jr/autonomy.json`
  `code_automerge: true`, C2 repository variable `JR_CODE_AUTOMERGE` not `0`, C3 a PASS naming THIS head
  (another sha is no verdict), C4 at most one agent-merged PR an hour (label `agent-pass`), C5 `gh pr merge
  --auto --match-head-commit <head>`, landing only when every required check is green there. A BLOCK labels
  the PR `needs-human` with the findings already in the comment; the author's next push is a new review;
  nobody waits.
- **An armed merge that cannot land never holds the hour (2026-11-20).** A merge requested with `--auto`
  counts as the hour's merge for as long as the PR stays open, and GitHub never merges a PR that conflicts
  with its base. #1851 (PASS, armed 03:14Z, conflicting) held the cap for every other reviewed PR until a
  person disarmed it at 07:55Z. So: C4b, a PR whose `mergeable` is `CONFLICTING` is never armed (GitHub
  computes that lazily, so `UNKNOWN` is asked again, three reads); and the hourly sweep takes back (auto-merge
  off, label dropped) an armed merge that conflicts or that was armed more than an hour ago and is still open.
  The one taken back for its age is decided again by the next sweep, not the same one, so it cannot take the
  hour it just gave back. A merge that could not be taken back still counts.

This is the one place an LLM sits in the loop, and it decides nothing the catalog shows: a wrong PASS is
caught by the same after-the-fact audit as a wrong human approval, and the switch turns it off in one
command. The action's agent mode is documented as experimental; the primary lane does not depend on it.

### 8. Jr keeps its own review PRs mergeable (2026-11-15)

**Why.** Every tick PR edits `jr/proposed_ledger.json`, so a `jr-review` PR conflicts with main as soon as
any other tick PR merges. A person then had to resolve it before the reviewer's exact-head approval meant
anything: three times on 2026-11-15 alone, and once (#1730) taking main's ledger would have dropped ~40
decisions that existed only in the PR.

**The refresh (`jr/review_refresh.py`).** After its own publish, each tick refreshes at most
`REFRESH_MAX` (2) of its own open review PRs, and only within the limits the reviewer set:
- the Jr bot's own same-repo tick PR (`pending_prs.eligible`), labelled `jr-review`, that GitHub reports
  `CONFLICTING`;
- every commit on it is the bot's: a PR carrying a human commit is never touched;
- the head is still the one the tick listed;
- every conflicted path is bookkeeping (`review_routing.is_bookkeeping`); a content conflict is left
  for a person;
- the ledger becomes `memory.merge_pr_ledger(main, merge base, PR head)`: main's, plus every record the PR
  changed under `carry_decisions`' rules, plus the PR's own proposals; `docs/telemetry/yield.jsonl` is
  main's rows plus every row the PR has and main lacks, keyed by (tick, stage), main's row on a shared key
  (`yield_ledger.merge_text`: taking main's file erased the review PR's own tick, i.e. every producing
  tick, and raised a false `stall:firmware`, incident 0cf1acb95f79, 2026-11-19); every other bookkeeping file is
  main's (a PR's own `jr/board_cooldown.json` entries are dropped and re-derived the next time that board
  fails, as for a superseded bookkeeping PR). `scripts/ledger_guard.py` must be green against main, and every catalog file the PR changed must
  be byte-identical to its head (a silent auto-merge into a reviewed file is refused);
- the result is a merge commit on top of the PR head, pushed without force (fast-forward only).
Anything else is a skip with the reason in the tick report; nothing is pushed. A dry run reports
`would_refresh`. The reviewer's exact-head content review stays the only human step.
