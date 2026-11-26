# SPEC — outcome attribution: what Jr's shipped changes did to site activity

Status: step B of the united plan (2026-11-26; Codex gpt-6-astra: "Jr lacks a closed loop from deployed changes
to activity outcomes and back to work selection"). Measurement only: it changes nothing Jr does.

## 1. Inputs (no new state)

- **Changes**: main's first-parent history. Each merge that adds or modifies a catalog record
  (`data/firmware/<id>/firmware.md`, `data/boards/<brand>/<id>/board.md`, `data/recipes/<b>__<f>/recipe.md`) is
  one change: its main SHA, its merge time (UTC), the canonical URLs it affects (`/firmware/<id>`, `/parts/<id>`;
  a recipe affects both its firmware and its board page), its kind (`added` / `modified`) and its lane (the
  merged branch: `jr/tick-*-bf` backfill, `jr/tick-*` tick, `jr/research-*` demand, other = person).
- **Activity**: Search Console page totals by page and date (`dimensions: [page, date]`), paginated, final data
  only. GSC dates are Pacific time; a change's day is its merge time converted to Pacific. Query rows are not
  used: they are privacy-filtered and row-limited (a missing query is not missing demand).

## 2. Effect per change cohort (difference in differences)

A cohort is the changes of one lane, kind and Pacific ISO week. For a window W (7, 14, 28 days):

- **pre** = page totals over the W days before the change day; **post** = over W days starting 3 days after it
  (indexing lag). New pages (kind `added`) have no pre: they are reported as post totals against the median post
  of the previous four weekly cohorts of the same lane (a cohort baseline, never a DiD).
- **control** = pages of the same type (firmware / parts) with no change in [day − W, day + 3 + W]; their
  pre → post ratio is the site-wide trend for that window.
- **effect** = treated (post − pre) − treated pre × (control post / control pre − 1), reported with the counts
  of treated and control pages. A window not fully in the past (or not final) is `immature`, never a verdict.

+7 and +14 are diagnostics; **+28 is the verdict**.

## 3. Output

A section in the daily telemetry digest and a JSON file in the runner's state dir
(`JR_STATE_DIR/outcomes-<date>.json`): per cohort {lane, kind, week, pages, windows: {7, 14, 28: {pre, post,
control_ratio, effect, mature}}}. Nothing is committed to main.

## 4. Non-goals

No allocation change here (step C, owner-gated). No SEO text. No record is written.
