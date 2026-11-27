# Demand work executor — the delegate's instructions

Status: the configured prompt SPEC-demand-work-consumer.md §Required execution path names
(2026-11-08). The operator's daily Jr job runs a coding delegate with this text once per live
work receipt that has no PR and no attempt today. One receipt per run. No host names, shell users
or credential paths belong here (the repository is public); the job supplies the checkout and the
branch.

## Inputs the job gives you

- `WORK_KEY`: the receipt's `key` in `docs/demand/work-receipts.json` (a 16-hex search key or a
  `pam-<24 hex>` market-lead key). `BRANCH`: the receipt's `branch` (`jr/research-<key>`), already
  checked out by the delegate harness; you never create another branch, never merge, never push to
  `main`, never ship.
- `TODAY`: the UTC date. Pass it as `--date` to every `jr/work_record.py` call.

## What you do, in order

1. **Read the work.** `python3 jr/work_record.py check --date TODAY` must report no problems. Read
   your receipt and, for a PAM key, its `candidate.feed.lead` (`source_id`, `name_hint`,
   `chip_hint`, `source_pointers`). For a search key read the term and its snapshot item in
   `docs/demand/<date>.json`. For a **hygiene key (`fix-…`)** read `candidate.quote`: the `record`
   (one `data/**/*.md` path), its `id`, the `quotes` the daily check found on none of the record's
   cited pages, and the cited `urls`; this work is the "Hygiene work" path below, not steps 2-4. For a
   **resolver key (`resolver-…`)** read `candidate.resolver`: the `vendor`, the gauge `field`, how many of
   the vendor's boards are `missing` it and which (`boards`); this is CODE work, the "Resolver work" path
   below, and you never edit a catalog record. Then `python3 jr/work_record.py attempt WORK_KEY --date TODAY` and
   commit it: `git add -A docs/demand && git commit -m "chore(demand): attempt WORK_KEY on TODAY"`.
   **Every `work_record.py` write below is committed on `BRANCH` the same way, right after it**: the
   receipts and queue live in `docs/demand/`, and a change left in the working tree is lost when the
   run ends. Commit only `docs/demand/` and the board files you authored; never leave anything
   untracked in the checkout.
2. **Research the exact identity against primary sources only.** A PAM feed hint, a store page or a
   reseller is a lead, never a source. Open the manufacturer's product page and datasheet/schematic.
   Decide which of these is true and stop at the first that fits:
   - **Not catalog content** (an accessory, a kit without one specific board, a software term, a
     proprietary code, a page that only names a board we already have): record it —
     `python3 jr/work_record.py settle WORK_KEY --state abandoned --reason "<one sentence with the
     evidence url>" --date TODAY`, commit (`chore(demand): settle WORK_KEY abandoned`) — then go to
     step 6 (the operator's relay opens the bookkeeping PR from `BRANCH`).
   - **Already catalogued under another id** (search `data/boards/` and `data/firmware/` for the
     identity, model numbers and aliases): `settle --state rejected --reason "already catalogued as
     <id>: <evidence>"`, commit, step 6.
   - **A real, distinct board with no live primary source** (the manufacturer's product page and
     datasheet/schematic are gone, answer no content, or serve the same page for any path; a store,
     reseller, wiki, PlatformIO or Arduino board list is not a primary source): nothing can be cited,
     so it cannot be catalogued. `settle --state abandoned --reason "no live primary source: <each
     manufacturer url you tried and what it returned>"`, commit, step 6. Do not leave it for the next
     day: the broker stops resuming any work without a PR after its second day anyway.
   - **A real, distinct board missing from the catalog**: continue.
3. **Record the validation before any catalog write.** Write a JSON file **outside the repository**
   (a temporary directory, never inside the checkout: an untracked file makes the clone dirty and
   every later executor run refuses to start) with `validated_by` (your
   job name and run id), `primary_sources` (the manufacturer urls you read), `expected_ids` (the one
   catalog id you will author, e.g. `arduino-nano-esp32`), `forbidden_ids` (sibling SKUs that must NOT
   appear, e.g. a V3 when you author the V4, `[]` when there are none), `notes` (what distinguishes the
   siblings). First `python3 jr/work_record.py adopt WORK_KEY --date TODAY` (every key: the committed
   queue row is what the closure verifies against), then
   `python3 jr/work_record.py validate WORK_KEY --json <file> --date TODAY`, then commit
   (`chore(demand): validate WORK_KEY`). The kind defaults to `catalog_part` for a PAM lead and
   `catalog_search` for a search term; do not override it.
4. **Author the record exactly as `AGENTS.md` says** (one-pass record authoring, cite-or-omit): every
   hard spec quoted from a cited primary url with a `verified` date, derived values with their
   derivation and both inputs cited, nothing from memory. Run `python3 scripts/validate.py` and
   `python3 scripts/check_sources_live.py` (both take no arguments and check the whole catalog);
   both must pass. Touch only
   `data/boards/<vendor>/<id>/board.md` (and its sources). Never edit `data/firmware/**`, recipes, Jr code or the
   demand files by hand.
5. **Open ONE draft pull request** from `BRANCH` to `main`, title
   `feat(catalog): <board name> (demand work WORK_KEY)`, body: the primary sources, the siblings you
   kept distinct, the validation summary, and the line `Demand work: WORK_KEY`. Label it `jr-review`.
   Then `python3 jr/work_record.py link WORK_KEY <pr url> --date TODAY`, commit the two demand files
   on the same branch (`chore(demand): link work WORK_KEY to draft PR #<n>`), and push the branch.
   **If your harness cannot push or open pull requests**, commit the record and stop here: the
   operator's relay pushes `BRANCH`, opens the draft PR, and runs the `link` command for you.
6. **Stop.** Leave every change committed on `BRANCH` (a settle too: the relay opens the
   bookkeeping PR from it). Review is the machine's: CI checks the schema, the live citations, every
   quoted span against the page it cites (`quotes`) and that the PR changes exactly what this work item
   says (`demand-guard`); when all of it is green the canary merges the PR itself (one a day, at its exact
   head) — or, on a quote the page does not hold, comments the quote and labels the PR `needs-human`, which
   your next attempt must fix (re-read the page; quote it as written, or omit the claim). The owner can
   still veto by closing. The daily runner verifies the deployed result and records the outcome. Never
   mark anything delivered yourself.

## Hygiene work (a `fix-…` key, source `quote_check`)

The record exists and is wrong in one specific way: a span written between double quotes in its
frontmatter does not appear on any page the record cites (`scripts/check_quotes.py`, which CI runs on every
PR and the daily runner over the whole catalog). Fix exactly that, nothing else:

1. `attempt` and commit as in step 1.
2. For each listed quote, open the cited pages (`candidate.quote.urls`) and find the passage the note
   meant. Then either **quote it as written** — copy the page's own words, including its spacing of
   units and its punctuation; an elision is written `...`; do not paraphrase — or, when the page does not
   say it, **drop the quote marks and the claim they carried** (cite-or-omit: a note may describe, it may
   not quote what is not there). A table row the page renders as cells is quoted as the page's text, not
   as a pipe-separated line you composed. A quote inside a quote uses single quotes.
3. Run `python3 scripts/check_quotes.py <record path>`: every quote PASS (or no quotes left). Run
   `python3 scripts/validate.py`. Touch only that record.
4. Validation (step 3 of the main path): `expected_ids` is `[<the record's id>]`, `forbidden_ids` `[]`;
   the kind defaults to `catalog_quote` (the record's quotes PASS at the merge). Commit, open the ONE
   draft PR titled `fix(catalog): <id> quotes (demand work WORK_KEY)`, `link`, push, stop (steps 5-6).

## Resolver work (a `resolver-…` key, source `gauge_gap`)

The model boundary (`CLAUDE.md`, "North star"): you solve a CODE problem; you never fill inventory. The
hourly tick's backfill (`jr/stage_backfill.py` → `jr/board_backfill.py`) fills board fields from each
vendor's documentation through deterministic extractors, and for this vendor × field it fills nothing (the
boards in `candidate.resolver.boards` are missing the field). Make the extractor exist and work:

1. `attempt` and commit as in step 1.
2. **Fixtures first.** Open the vendor's documentation for 2-3 of the listed boards (the URL candidates in
   `jr/board_doc_resolvers.py` for that vendor, or the pages the boards' own `sources[]` cite). Save each
   page as it is served under `jr/fixtures/doc_resolvers/<vendor>/<board-id>.html` (or `.pdf.txt` for the
   text of a PDF), with a `SOURCES.md` beside them naming each fixture's URL and the date you fetched it.
   Never edit a fixture's content.
3. **RED test.** Write `jr/test_vendor_<vendor>_<field>.py`: for each fixture, the value the extractor must
   return, copied from the page (the manual-download steps sentence, the bridge chip, the dimensions as the
   page states them, …), and one page that does NOT state the field returning None. Run it: it must fail.
4. **The extractor.** Implement it in `jr/vendor_extractors/<vendor>.py` (create the package if absent) as a
   pure function over the page text, register it for that vendor and field where `jr/board_backfill.py`
   dispatches per brand (`_extract_for` / the per-brand tables), and add the field to the fields the backfill
   writes for that vendor if it is not there. Cite-or-omit is the extractor's law too: it returns a value
   only when the page states it, and the backfill writes the `sources[]` row of the page it read. Run
   `cd jr && python3 -m pytest test_vendor_<vendor>_<field>.py test_stage_backfill.py test_board_backfill.py -q`:
   green.
5. **Nothing else changes.** Only `jr/**` (code, fixtures, tests) and `docs/demand/` bookkeeping; never
   `data/**`, never a workflow. Do not run the backfill against the catalog yourself; the hourly tick does.
6. Validation (step 3 of the main path): `expected_ids` is exactly `candidate.resolver.boards`,
   `forbidden_ids` `[]`, `primary_sources` the fixture URLs; the kind defaults to `resolver_live` (the runner
   counts, after the merge, which of those boards the backfill filled; three or more delivers). Commit, open
   the ONE draft PR titled `feat(jr): <vendor> <field> extractor (demand work WORK_KEY)`, `link`, push, stop.

## Rules

- If any step cannot be completed with evidence, stop after recording what you know: a `settle`
  with the reason when the lead is not a board, otherwise nothing — the receipt keeps its attempt
  and the next day retries. Never guess a spec, never widen the scope to other boards, never run
  Jr's tick, drain or demand runner.
- `work_record.py` refuses a change the broker would defer on. If it refuses, report its message
  verbatim and stop; do not edit the JSON files by hand.
