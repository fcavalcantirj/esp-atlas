# Handover — EspAtlas Jr board-authoring lane (2026-08-28)

## Goal
Map every remaining ESP32-family board in `COVERAGE.md` (62 backlog at session start,
76 already done) — **using EspAtlas Jr** to author cited board records autonomously.

## ⚠️ REALITY CHECK — Jr does NOT work yet
**Jr has NEVER successfully authored a single board. Not once.** Across every live run
this session (gpt-oss-120b free, then paid gpt-4o-mini drafter+oracle) the outcome was
always the same: `{'action': 'none'}` → "🤖 Jr board batch — 0 new boards proposed."
**Zero cited PRs. Zero boards on main from Jr.** The 4 Espressif boards were authored by
the coding *delegate*, not by Jr.

"Built + 99 unit tests green + cost-capped + observable" is TRUE but is NOT "working" —
the end-to-end pipeline has produced nothing. Do not call this done, solid, or working
until a run actually opens a real cited board PR that survives review. It has not.

## What shipped today (all merged to `origin/main`, each validated before merge)
1. **4 Espressif boards** hand-driven via delegate — `esp32-c5-devkitc-1`,
   `esp32-c61-devkitc-1`, `esp32-ethernet-kit`, `esp32-lyrat`. (`8348733`)
2. **Jr's board-authoring lane, built from scratch** (Jr was firmware-only before):
   - `jr/tools.py`: `coverage_backlog()`, `fetch_url()`, `author_board()`,
     `board_triple_validate()` (schema + sources-live + **chip-family cross-check**),
     `board_refs()`, `oracle_review()`, per-model `record_spend()`.
   - `jr/models.py`: model factory — `JR_BOARD_MODEL` / `JR_ORACLE_MODEL` as
     `provider:model_id` (groq | openrouter).
   - `jr/oracle.py`: LLM fact-checker gate (fail-closed).
   - `jr/agent.py`: `make_jr_board` — drafter with **authoring-only** toolset.
   - `jr/run.py`: `boards_batch(n, vendor)` — drafter → oracle → guard → cited PR;
     `$5/mo` cap enforced + INFO logging on by default.
   - **~95 tests** green; `scripts/validate.py` 196/196.

## Model config (in `~/.config/jr/keys.env`)
- `JR_BOARD_MODEL=openrouter:openai/gpt-4o-mini`  (paid, ~$0.15/$0.60 per M)
- `JR_ORACLE_MODEL=openrouter:openai/gpt-4o-mini`
- Free `z-ai/glm-5.2:free` oracle was **HTTP 429 rate-limited** → switched to cheap paid.
- **`$5/month` hard cap** now tracked (`jr/spend.json`) on the board path. Unknown models
  priced at a conservative `$1/$3` per M so the cap trips early. **Spend so far ≈ $0.47.**

## Current state — subproblems fixed, SYSTEM STILL 0/0
Individual bugs got fixed (chip-identity: the oracle now understands `soc ← module ←
board`, "ESP32-WROOM"→`esp32`, and flags non-ESP-primary boards like the Inkplate's
STM32). But **the system as a whole has still never produced a board.** Each fix just
revealed the next rejection reason. The guards work (no garbage reached main), but that
is only half the job — nothing *good* has made it through either. Net board output from
Jr: **0.**

## The remaining blocker (start here tomorrow)
Latest run (`adafruit-metro-esp32-s2`) passed chip-identity but the oracle rejected
**spec-value fields** as *"not supported by the page"*: `form_factor`, `dimensions_mm`,
`power`, `io`. This is **cite-or-omit working** — the drafter is including fields the
*fetched page text* doesn't clearly back. Two candidate fixes (likely both):
- **(a) Drafter conservatism** — instruct `make_jr_board` to author ONLY fields it can
  quote from the fetched page; OMIT `form_factor`/`dimensions_mm`/`io`/`power` when absent.
- **(b) Better page capture** — `fetch_url()` likely strips the specs/dimensions/pinout
  sections; capture them so the oracle *can* verify the fields the drafter includes.

## Next steps (tomorrow)
1. Fix drafter-overinclusion vs page-coverage (a and/or b above).
2. Re-run `python jr/run.py boards` → expect Jr's **first real cited board PR**
   → review hard, **merge if perfect** (Felipe: I merge if all-perfect).
3. Scale: `boards_batch` across the 58 remaining backlog boards, vendor by vendor,
   each a cited PR. Watch the `$5` cap.

## Known minor issues / notes
- **Orphan hygiene:** `boards_batch` retry path can leave untracked board dirs behind
  (they pollute whole-dataset validation + `coverage_backlog` filesystem dedup).
  Cleanup-on-crash covers the exception path; the retry-supersede path still orphaned a
  dir in some runs. Cleaned manually this session; worth a proper fix.
- **Merge policy:** esp-atlas is NOT in `~/.dasbrowcoder/merge-policy.json`, so the
  delegate's auto-merge REFUSES — manual merge to main (fine). Add to allowlist if wanted.
- **Oracle spend** is now recorded, but verify it's counted when the oracle is paid.

## Footguns learned (do not rediscover)
- **Agno + Groq/OpenRouter:** do NOT pass `base_url` — it double-appends the path →
  404. Let the Agno model class default.
- **Agno tool schema:** a `**kwargs` catch-all OR a param with no default becomes a
  **required** JSON-schema property → weak models fail with `missing properties: 'x'`.
  Keep tool signatures minimal-required; give defaults.
- **Weak drafter (gpt-oss-120b):** misuses tools it doesn't need → give the drafter
  ONLY authoring tools; the pipeline owns validation.
- **Free OpenRouter models:** rate-limited (429) → unreliable as a gate; use cheap paid.
- **Mocked unit tests hide endpoint/schema-gen bugs** — verify against the REAL client /
  a live run, not just green tests.
- **The coding delegate can no-op and falsely report PASS** on prompt-tuning tasks
  (rationalizes "already handled"). ALWAYS verify `git diff` is non-empty before trusting.
