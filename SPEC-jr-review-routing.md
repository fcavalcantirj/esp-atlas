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
- a star/date refresh of an **existing** record: the only frontmatter differences are the
  `popularity` block and `sources[].verified` dates, and the body is unchanged.

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

### 4. Tick report

`TickReport.review_prs` lists every open `jr-review` PR with its age; the one-line report renders
`jr-review open N: #12 30h, …`. A tick that opens a review PR notifies Telegram like `needs_human`.
