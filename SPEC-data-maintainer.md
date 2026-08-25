# SPEC — autonomous data-maintainer (fx-open on the Pi)

> Status: DRAFT → building. The concrete **implementation** of the data lifecycle
> specced in `SPEC-freshness.md` (maintain), `SPEC-data-population.md` (grow), and
> `SPEC-discovery.md` (harvest). Those say *"a bot proposes cited PRs; CI + a human
> gate them."* This spec is the **bot**: a headless `fx-open` agent running daily on
> the always-on Raspberry Pi, on our own Groq/OpenRouter keys.

## 1. Why fx-open, and why it's safe
`fx-open` = Vercel's `fx` coding agent, forked to run on Groq/OpenRouter (BYO key),
a tiny native binary with headless JSON mode (`fx ask --yolo --no-save --json`) and
real tools (read/write/list/grep files + `run_command` shell + MCP).

**Safety is by construction — the blast radius is a PR, nothing more:**
- esp-atlas `main` is **branch-protected**: the agent **cannot push to main and cannot
  merge**. It can only push a `maintainer/*` branch and `gh pr create`.
- Every PR hits the **existing CI gate**: `schema` + `sources-live` (every cited URL
  must be 200) + oracle (no-orphans, valid trust-tier). A hallucinated spec with a
  dead citation **fails and never merges**.
- **A human merges.** Always. (`SPEC.md` governance, inherited.)
- So the agent does **not** need to be smart or trustworthy — the gate makes a cheap
  model safe. This is the whole point.

## 2. Runtime & isolation
- **Host:** the Pi (always on, already has `gh` authed, Python, the repo).
- **Binary:** `~/.local/lib/fx-openai-compat/fx` + launcher `fx-groq` (Groq free-tier
  is the daily driver; `fx-openrouter` for heavier models when needed).
- **Keys:** `~/.config/fx-open/env` (chmod 600, gitignored/outside every repo, never
  committed, never posted anywhere public).
- **Workspace:** a dedicated clone at `~/code/esp-atlas-maintainer`, `git pull`ed to
  latest `main` at the start of every run; the agent works only there.
- **fx config:** `FX_PERMISSION_MODE=auto` (the command auto-classifier gates risky
  ops; NOT raw `yolo`), `FX_MAX_AGENT_STEPS` bounded, `.fx.json` sandbox on. Even so,
  the branch-protection gate (§1) is the real boundary.

## 3. The daily run (one cron tick)
1. `git -C ~/code/esp-atlas-maintainer fetch && reset --hard origin/main` (clean slate).
2. Run `fx-groq ask --yolo --no-save --json "<TASK>"` with a bounded step budget.
3. The agent executes **one focused job per run** (rotates / picks highest-value):
   - **Freshness** (`SPEC-freshness.md`): re-check `sources[].url` liveness; check
     firmware GitHub releases vs recipe `firmware_version`; flag recipe drift.
   - **Grow** (`SPEC-data-population.md`): pull the next uncovered board from an
     official catalog (Arduino `package_<vendor>_index.json`, Launcher wiki, M5Burner),
     author a schema-valid, **cite-or-omit** record.
   - **Discover** (`SPEC-discovery.md`): a "with-code" candidate from awesome-esp32 /
     GitHub trending → firmware / prompt-recipe / example, cited.
4. It **runs `scripts/validate.py` + `check_sources_live.py` locally** and only opens a
   PR if they pass — so most bad drafts die before they ever reach CI.
5. `git checkout -b maintainer/<job>-<date>` → commit (conventional) → `gh pr create`
   with a label (`maintainer:freshness|grow|discover`) and the cited sources in the body.
6. Auto-harvested records land `status: unverified`; trust promotion stays human-only.

## 4. Task prompts
Stored in `~/code/esp-atlas-maintainer/.maintainer/` (one prompt per job kind), each
encoding the relevant spec's rules verbatim: official-source-first, no scraping,
cite-or-omit, one focused change, run the validators, open ONE PR, never touch main,
never merge, if unsure open an Issue instead of guessing.

## 5. Cost & cadence
- **Groq free-tier** is the default (no per-call cost); `gpt-oss-120b` / `gpt-oss-20b`.
- **OpenRouter** only when a run needs a stronger model (keep a few $ — it pre-reserves
  credit for `max_tokens`).
- Cadence: **daily** (cron), one focused job per tick → a steady trickle of small,
  reviewable PRs rather than one giant dump. Volume-capped so review stays humane.

## 6. Non-negotiables (inherited)
Cite-or-omit · official APIs, no ToS-violating scraping · bot proposes, humans dispose ·
auto = `unverified`, promotion human-only · never writes/merges `main` · one focused
PR per run · logs every run.

## 7. Out of scope
Not a merger (humans merge). Not a validator rewrite (CI is the gate). Not the site.
