# SPEC — Zero-Result Site-Search Research Queue (Jr's research lane)

> **One zero-result search is a research question, never an authoring order.** Classify
> *why* the site found nothing — missing content, an alias/typo, or search behavior — before
> anyone proposes a change. Jr never writes catalog content from it. (Felipe, 2026-11-04.)

This spec adds a second, separate path out of the D2 site-search lane of
`SPEC-jr-demand-driven.md`. The demand steer is unchanged: `MIN_EVENTS = 5` still floors every
site-search term before it can become a `DemandItem` (§3.3 there). Today every typed term has
~1 search, so the floor drops all of them — correctly for steering, but it also threw away the
strongest catalog-gap evidence the site has. The research queue keeps it.

## Input

The same GA4 pull the miner already makes (`eventName` × `customEvent:q`, events
`search_submit` / `search_empty`, the miner's 28-day window). Per normalized term:

- `searches` — the term's `search_submit` count in the window;
- `zero_result_searches` — the term's `search_empty` count in the window.

A term is a **candidate** when `zero_result_searches >= 1` **and** `searches >= 1`. A term that
returned results creates nothing, however often it was searched.

## The queue file — `docs/demand/research-queue.json`

```jsonc
{
  "version": 1,
  "max_new_per_day": 5,
  "reopen_after_days": 30,
  "candidates": {
    "esp32 c6": {                          // key: normalized term (see Dedupe)
      "term": "esp32-c6",                  // first wording seen (the miner lowercases it)
      "first_seen": "2026-11-04", "last_seen": "2026-11-05",   // intake dates (the miner's run day)
      "source": "ga4 search_empty",        // which signal produced the counts
      "window": {"start": "2026-10-08", "end": "2026-11-05"},   // the GA4 window the miner queried
      "searches": 1, "zero_result_searches": 1,   // latest window that saw it, NOT a running sum
      "status": "new",                     // new | validated | linked | closed
      "classification": "search_defect",   // alias_typo | search_defect | missing_content | unclear
      "evidence": {"rule": "...", "ids": ["esp32-c6"], "matches": [{"id", "kind", "via", "label", "distance"}]},
      "linked_work": [],                   // PR / issue / branch refs, set by a human
      "outcome": null,                     // set when the candidate is closed
      "closed_on": null,                   // YYYY-MM-DD, set when closed
      "history": []                        // prior closures, appended on reopen
    }
  }
}
```

- **Append-only.** The miner adds candidates and refreshes `last_seen` / counts; it never
  deletes a candidate and never overwrites `status` beyond `new`, `linked_work`, `outcome` or
  `closed_on`.
- **Counts are a window, not a total.** The GA4 window overlaps day to day; summing daily
  pulls would multi-count the same search. `searches` / `zero_result_searches` are the latest
  window's values.
- **Provenance.** `source` names the signal (`ga4 search_empty` for the miner) and `window` is
  the exact `start`/`end` the miner queried (`_pull_live`'s window) — the window the counts come
  from. Both refresh with the counts; `first_seen` / `last_seen` stay intake dates and are never
  derived from the window.
- **Classification refreshes only while `new`.** An untriaged candidate always reflects the
  current catalog; once a human moves it on, the record is theirs.

## Dedupe

The key is the term case-folded with every run of non-alphanumerics (whitespace, punctuation,
`-`, `_`) collapsed to one space: `ESP32-C6`, `esp32 c6`, ` esp32_c6! ` → `esp32 c6`. Letters
and digits are Unicode-aware: `Módulo` → `módulo`, `开发板` stays a term.

## Rate limit

- The cap and reopen window are the queue file's own `max_new_per_day` / `reopen_after_days`
  (defaults 5 / 30), so a hand edit there is what the miner enforces.
- At most `max_new_per_day` (default **5**) candidates are opened per day. A reopened
  candidate counts as opened. Same-day reruns are idempotent: candidates opened earlier the
  same day count toward the cap. Ordering is deterministic (most zero-result searches, then
  most searches, then key). Terms over the cap are **deferred** — reported, not written; the
  28-day window brings them back on a later day.
- A `closed` candidate is **never reopened within `reopen_after_days` (30)** of its
  `closed_on` (falling back to `last_seen` when unset), and is left untouched meanwhile. With
  no readable date at all it is never reopened (fails closed); `close` accepts only YYYY-MM-DD.
  After that, a new zero-result sighting reopens it as `new`, reclassified, with the prior
  closure appended to `history`.

## Classification — pure, offline, explicit evidence

Against the catalog index: every id, `name` (title) and `aka` (alias) of `data/boards`,
`data/firmware`, `data/socs` + `data/modules` (the parts behind `/parts/<id>`) and
`data/brands`. Labels compare in compact form (alphanumerics only, so `t-beam` = `tbeam`).
First rule that fires wins:

1. **`search_defect`** — the term equals a catalog **id or title** exactly, yet the search
   returned zero results. Evidence: the matching ids. (A bare `esp32` is an id: a defect.)
2. **`unclear`** — the term carries no identity: compact form under 3 characters, or every
   token is a generic word (`esp32`, `board`, `firmware`, …).
3. **`alias_typo`** — the term fuzzy-matches an id, title or alias: an exact alias match, the
   same identity tokens in any order (generic words dropped: `marauder` ~ `ESP32 Marauder`), or (for terms of 4+ compact characters) an edit distance
   within `1` (`2` for terms of 10+). Evidence: the matching ids with `via` and `distance`.
   More than 3 distinct ids → `unclear` (ambiguous, evidence kept).
   Positive edit distance does not establish equivalence between digit-bearing board/part
   model identifiers: `ES3N28P` is not an alias for `ES3C28P`. Exact aliases, the same identity
   tokens and exact vendor-prefix/model matches remain valid; ordinary word and firmware
   typo matching is unchanged. A nearby physical model stays a research candidate until its
   identity is checked against a primary source.
4. **`alias_typo` (vendor-prefix / model number)** — only when rule 3 found nothing: board ids
   are vendor-prefixed (`freenove-fnk0104s`), so a search for the bare model number never
   equals an id. The term (compact) equals a record's **model key** — its id without the
   `<brand>-` prefix (`fnk0104s`), or a token of its title (`ESP32-S3 Display FNK0104S` →
   `fnk0104s`). Evidence: that id, `via` `id`/`title`, distance 0, and a rule naming the
   vendor-prefix match. A key is a model number only if it is 5+ characters, holds a letter
   and a digit, is not a generic word, and **exactly one** record carries it in any id, title
   or alias (as a run of consecutive tokens, the whole label included) — so `esp32`, `s3`, `lite`, `display`, `18650` or a token two
   records share never match, and `fnk0104s` never matches its siblings `fnk0104a` /
   `fnk0104b`. An id suffix counts only if one of its own tokens is a model number, so short
   words never join into one (`s3 mini` does not match `lolin-s3-mini`).
5. **`missing_content`** — nothing in the catalog matches. Evidence: no ids, plus how many
   catalog entries were checked.

## What it never does

- It **never writes under `data/`**. Its only outputs are the queue file and one line in the
  demand digest (and the daily demand PR body).
- It never authors, proposes or opens a catalog record. A candidate becomes work only when a
  human validates it.

## Lifecycle — connecting candidates to work

`python jr/research_queue.py <command> <term> …` edits the queue file (and nothing else):

| command | from status | effect |
|---|---|---|
| `validate <term>` | `new` | `status = validated` |
| `link <term> <ref>` | `validated` / `linked` | append `ref` to `linked_work`, `status = linked` |
| `close <term> <outcome>` | any open | `status = closed`, `outcome`, `closed_on = today` |

A `linked` candidate that keeps showing up zero-result still refreshes `last_seen`, so the
digest can show linked work that has not fixed the search yet.

## Wiring

`jr/demand.py`'s `mine()` updates the queue after the snapshot; `jr/demand_run.py` lands
`research-queue.json` alongside the snapshot and `unresolved.json` (all under `docs/demand/`,
which `jr/review_routing.py` routes AUTO as bookkeeping). A run whose snapshot is unchanged
but whose queue changed still lands — a change in `last_seen` alone does not count (an open
candidate is re-sighted daily while the window holds it; the weekly refresh carries it), nor
does `evidence.checked` growing with the catalog, nor the GA4 `window` sliding a day.

**Queue-only run.** A successful miner run (exit 0, snapshot written) whose snapshot has **zero
items** is still refused as a steer — it is an outage far more often than zero demand. But when
the research queue changed (same comparison as above), the runner lands a **queue-only** PR: it
stages `docs/demand/research-queue.json` alone and restores every other `docs/demand/*.json` the
miner touched, so neither the dated snapshot nor `unresolved.json` is replaced or added. Zero
items with an unchanged queue (including an identical rerun of a landed queue-only run) still
aborts, as does a failed miner. A missing queue file compares equal to an empty queue, so an
outage that only creates an empty queue aborts too. A queue-only PR lands on
`jr/demand-queue-…`. Queue-bearing PRs are never automatically superseded: this includes
queue-only branches AND ordinary demand snapshot PRs that change the queue. Each fresh run
starts from main and may not have read an earlier unmerged PR's candidates, lifecycle status,
linked work or outcomes. A newer queue changing is not proof those were preserved. Only a
PR with a complete, readable changed-file manifest proving it contains dated snapshots and/or
`unresolved.json` alone can be closed automatically. Missing, malformed or truncated manifests,
and renames whose original paths are not known, retain the older PR for review.
Consolidating queue-bearing PRs requires checking their full
candidate lifecycle data before closing them.

**Atomic write.** `write_queue` writes a temp file in the queue's own directory, flushes and
fsyncs it, then `os.replace`s it over the queue. An `OSError` anywhere leaves the previous file
byte-identical, removes the temp file and is raised — so `mine()` reports `research queue NOT
updated` and the runner sees no queue change, never a truncated queue. A queue or catalog error never blocks the
snapshot: the miner leaves the queue file untouched and the digest says `research queue NOT
updated`. Dated-snapshot readers (`demand_signal.load_latest`, the
runner, the miner's `first_seen` carry-forward) read only `<YYYY-MM-DD>.json` files.

## Invariants (tested — `jr/test_research_queue.py`, `jr/test_demand_research.py`)

- one zero-result search → exactly one candidate; the same term in another case → one;
- the 6th new candidate on one day is deferred;
- a term with no catalog match (the made-up SKU `zz9q41x`) → `missing_content`;
- `es3c28p` → `alias_typo` with exactly `lcdwiki-es3c28p` (its alias; the vendor-prefix rule
  alone lands on the same id); the distinct sibling `es3n28p` never resolves to that touch board;
- one typo away from a board id → `alias_typo` with that id as evidence;
- a bare model number (`fnk0104s`) → `alias_typo` with exactly its vendor-prefixed id;
- equal to an id but zero results → `search_defect`;
- a closed candidate is not reopened within 30 days;
- a term with results and 1 search creates nothing;
- `MIN_EVENTS` steering unchanged;
- each candidate carries `source` and the queried GA4 `window`; only terms with a
  `search_empty` event become candidates;
- zero demand items + a changed queue → a queue-only PR; the dated snapshot is untouched;
- fresh main-based runs never close/delete an older queue-bearing PR, including a normal
  demand PR, and unknown/incomplete changed-file manifests cannot authorize superseding;
- a failed queue write leaves the previous file byte-identical and is surfaced;
- nothing under `data/` is written.
