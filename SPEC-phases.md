# SPEC — phased plan: real inference, a working data agent, an AWESOME site

> Status: DRAFT. Written after Felipe's feedback that "the AI feels like regular
> search" and "fx-open is horrible." Three phases, in order. Phase 1 must land before
> Phase 2. Uses the oracle-loop (invariant tests) where noted.

## 0. First, the confusion answered — what Groq actually does, how, why
Right now the home "intent box" feels identical to search **because it IS search** —
it is NOT wired to Groq yet. That is the bug, not the design. There are TWO distinct
inference jobs, and today only one is even partially built:

**A) Intent→filters (the home smart box) — THE missing piece.**
- Free text in ("a board to detect plant humidity") → Groq returns a small **STRUCTURED
  JSON** object of real filter keys, e.g. `{"radio":"wifi","battery":true,"budget":"cheap"}`.
- We run THOSE filters over the catalog → real boards.
- The UI shows **what it understood** (chips: `Wi-Fi · battery · low cost`) + **why each
  board matched**. That is what makes it visibly different from search.
- **Why Groq → JSON (not prose):** the inference only *translates* human words into
  filters the engine already has; the **data answers**, so results can't be
  hallucinated. It's cheap (cache by the query string, catalog-size-independent) and the
  "why" is grounded. Inference translates; data answers.

**B) Ask (the /ask chat) — RAG.**
- Free text question → retrieve relevant records → Groq writes a **grounded, cited**
  answer (never asserting what the data can't support). This is genuine free-text-out,
  but its value is the synthesis + citation, not a keyword dump.

So "where is the inference?" → job A isn't wired to Groq yet (keyword stub), and job B
needs to visibly cite. Phase 1 fixes both.

## Phase 1 — Groq answers NICELY (the inference is real + visible)
1. **Wire the intent box to Groq (job A).** Model `openai/gpt-oss-20b` (cheap/fast).
   Output constrained to known filter keys only (reject invented keys). Firmware intents
   ("run marauder") route to the recipe path. Cache by query string.
2. **Show the inference in the UI.** Derived-filter chips + per-result reasoning. Kill
   "N parts match via search" for intent queries. Honest fallback if unmappable.
3. **Ask (job B) visibly grounded** — cited, never false-absence (already fixed in #38).
4. **Oracle-loop acceptance (write as tests, loop to green):** "plant humidity" →
   `{wifi,battery,cheap}` + shown reasoning, NO Inkplate noise; "run marauder" → recipe
   path; "esp32-s3 8mb psram" → exact filter; nonsense → honest fallback. Add `battery`
   (`power.battery_connector`, 46 boards) as a real indexed filter.
**Phase 1 is the gate — nothing else ships until the box genuinely infers.**

## Phase 2 — a data agent that actually works
**fx-open is DROPPED** (tested, poor). It builds/runs on the Pi but the agent quality is
not good enough. Re-evaluate, headless + cheap/free-model + reliable tool-use + Pi-able:
- **Candidate 1 (smaller step): Kimi CLI** — `github.com/MoonshotAI/kimi-cli`, on
  Moonshot/OpenRouter free models. Test the same round-trip bar fx passed, then a real
  freshness PR against esp-atlas.
- **Candidate 2 (bolder, later): openviking.ai + openclaw/hermes** on open/free models —
  a bigger change; only if Kimi under-delivers. Phase it; don't bet the pipeline on it.
- **Safety is now REAL:** repo is public → enable branch protection (require PR + CI +
  review, **enforce for admins**) so the agent literally cannot merge/push main. The
  "blast radius is a PR" model becomes enforced, not convention.
- Same rails regardless of engine: seeds.json → cited PRs → CI + human merge → EspAtlas Jr.
- **Acceptance:** the agent opens ONE real, cited, CI-green PR unattended; a human merges.

## Phase 3 — improve
Discovery breadth, prompt-recipes, the flash hub polish, analytics-ranked examples,
richer fields (the sensor/ADC gap), more firmware. Only after 1 + 2 are solid.

## The site must be AWESOME — a living tool (runs alongside)
- Footer: the one-liner + `/how-we-work` page + EspAtlas Jr. (already dispatched).
- **Gorgeous mission tagline** (pick one), placed in the hero or footer:
  - "The living map of the ESP32 world."
  - "Every ESP32 — mapped, cited, alive."
  - "Chip to running: fast, honest, alive."
  - "The ESP32 world, kept honest — and current."
- Living-tool feel: freshness shown not hidden, the daily agent visible, examples that
  breathe. Spec each UI change before building; oracle-loop the invariants.

## New seeds added
`M5RogueOps/Periscope-OS`, `espressif/esp-claw` → seeds.json firmware_releases.
