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
   `docs/demand/<date>.json`. Then `python3 jr/work_record.py attempt WORK_KEY --date TODAY`.
2. **Research the exact identity against primary sources only.** A PAM feed hint, a store page or a
   reseller is a lead, never a source. Open the manufacturer's product page and datasheet/schematic.
   Decide which of these is true and stop at the first that fits:
   - **Not catalog content** (an accessory, a kit without one specific board, a software term, a
     proprietary code, a page that only names a board we already have): record it and stop —
     `python3 jr/work_record.py settle WORK_KEY --state abandoned --reason "<one sentence with the
     evidence url>" --date TODAY`.
   - **Already catalogued under another id** (search `data/boards/` and `data/firmware/` for the
     identity, model numbers and aliases): `settle --state rejected --reason "already catalogued as
     <id>: <evidence>"`.
   - **A real, distinct board missing from the catalog**: continue.
3. **Record the validation before any catalog write.** Write a JSON file with `validated_by` (your
   job name and run id), `primary_sources` (the manufacturer urls you read), `expected_ids` (the one
   catalog id you will author, e.g. `arduino-nano-esp32`), `forbidden_ids` (sibling SKUs that must NOT
   appear, e.g. a V3 when you author the V4, `[]` when there are none), `notes` (what distinguishes the
   siblings). For a PAM key first `python3 jr/work_record.py adopt WORK_KEY --date TODAY`, then
   `python3 jr/work_record.py validate WORK_KEY --json <file> --date TODAY`. The kind defaults to
   `catalog_part` for a PAM lead and `catalog_search` for a search term; do not override it.
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
6. **Stop.** Review and merge are the owner's; the daily runner verifies the deployed result and
   records the outcome. Never mark anything delivered yourself.

## Rules

- If any step cannot be completed with evidence, stop after recording what you know: a `settle`
  with the reason when the lead is not a board, otherwise nothing — the receipt keeps its attempt
  and the next day retries. Never guess a spec, never widen the scope to other boards, never run
  Jr's tick, drain or demand runner.
- `work_record.py` refuses a change the broker would defer on. If it refuses, report its message
  verbatim and stop; do not edit the JSON files by hand.
