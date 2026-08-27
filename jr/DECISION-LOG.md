# EspAtlas Jr — Decision Log & Reset Point (2026-08-27)

> **Status: PAUSED for a rethink.** `jr-daily` cron is paused. Resume decision scheduled
> **Monday 2026-08-31, 16:00 BRT.** Read this before touching Jr again.

## The honest verdict

**Jr has NOT autonomously produced a single clean, merge-ready PR.** Every firmware that
landed or was proposed needed human intervention:

| PR | What happened |
|---|---|
| #69 evil-m5project | agent socs were right, but it **broke `main`** (missing coverage run-case) → fixed in `260156f` |
| #70 coverage recipes | **hand-authored by the operator**, not the agent |
| #71 CatHack | agent **fabricated `esp32-s3`** for an esp32 board → socs **hand-corrected** before merge |
| #73 advanceos/porkchop | agent wrote **freeform capabilities** ("Media playback (MP3, WAV)") → **hand-fixed** |
| #74 Marauder | **fork of catalogued esp32marauder** → junk, closed |
| (terminated run) | left **garbage ids** (`shark-2024-08-1`…) — purged |

So the "wins" reported during the session were the operator patching the agent's output.
Do not repeat that self-deception.

## Root cause (architectural, not tokens)

The design puts a **weak free model (Groq `gpt-oss-120b`) in the JUDGMENT seat** for things
that are mostly **lookups**: which board, which category, capabilities-as-tokens, a clean id,
is-this-a-fork. It fails at these, and the session was spent **whack-a-mole patching** each
failure. It does not converge.

**The catalog already has the structured data** the LLM was made to re-guess:
`api.launcherhub.net/giveMeTheList` entries carry `github`, `category`, `tags`, `download`,
and the device is in the `name` ("Bruce **for StickC plus2**"). We ignored it and read READMEs.

Cost note: measured **~$0.08/run** (≈488k tokens — the agent iterates many candidates), not the
$0.004 first estimated. The **$5/month hard cap is enforced** (`jr/spend.json` + `month_spend()`),
so overspend is impossible — but optimizing token cost of a bad generator is the wrong axis.

## The direction (Felipe's call, 2026-08-27)

Build a **deterministic, versioned, improvable scoring/authoring helper** (an API / CLI /
function) that the agent *runs and uses* — rather than the LLM guessing. Shape:

- **Input:** a launcher-catalog entry (+ the repo).
- **Deterministic logic:** `github` → repo/real-stars/fork-check; parse device from `name` via a
  `device → board` map → board + chip (chip already derived from board records via `board_soc`);
  `category`/`tags` → our enum + capability **tokens** via a fixed map; id = clean slug from repo.
- **Output:** a **score** (is this a clean, genuinely-new, mappable firmware?) + the authored
  record if score is high enough, or a skip/Issue reason.
- **Versioned + tested:** it's an algorithm we improve with **spikes + a real test suite** (golden
  cases: known firmware → expected record), not prompt-tweaking.

The LLM shrinks to little/none (maybe a fallback category classifier). Deterministic guard +
human-merge still gate. **We need way more tests and spikes before trusting any of it.**

## What's salvageable (keep)

`board_soc()` chip-derivation · the deterministic guard (`validate.py`) · `triple_validate` gates
(schema/source/structure + soc cross-check) · the CI-test gate + `author_run_case` · the
`proposed.json` dedup ledger · the `$5/month` spend cap · **telemetry** (GA4+GSC via Composio
OAuth — `jr/telemetry.py`, works, `jr-telemetry` cron Mon 09:07, standalone digest, NOT wired into
authoring). The rot is specifically the **LLM-judgment authoring path** in `agent.py` /
`author_firmware_and_recipes`.

## State on ice
- `jr-daily` cron: **PAUSED** (id `9fcfd475b05b`).
- `jr-telemetry` cron: active (harmless weekly numbers digest).
- Open PRs: **#38** (old, non-Jr `/ask` feature — product decision, sources actually alive).
- Jr code on `main`; the deterministic pieces above are committed and working.

## Monday 16:00 — resume plan
1. **Spike** the deterministic scorer against 10–20 real launcher entries with known-correct
   expected records (golden set). Measure accuracy with **zero LLM**.
2. Build the `device → board` map + `tags → capability-token` map (small, versioned, tested).
3. Add a **fork/dup detector** that actually works (name-token + repo lineage).
4. Only then decide if/where the LLM belongs. Keep `jr-daily` paused until the scorer beats the
   agent on the golden set.
