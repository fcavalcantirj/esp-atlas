# Builder handover #2 — flash UI (P2b) and beyond

> Succeeds `2026-08-24-builder-handover.md`, which covered L1. Written by the
> outgoing builder at the end of the L1/L2-backend session, for the agent taking
> over. **Validate before you trust it**: re-check anything marked ⚠️, and spike
> where you are unsure rather than assuming. Where this doc and the code
> disagree, the code wins — say so in the room.

## Context — why you exist
Felipe owns **esp-atlas** (`github.com/fcavalcantirj/esp-atlas`, live at esp-atlas.com):
a cited, queryable knowledge base of every ESP32 SoC / module / board, plus a
firmware "what runs on what" recipe graph and an in-browser flash hub.

You are the **executor/builder**. The **architect** is the agent `dasbrow_brains`,
reachable only in the Solvr room **`esp-atlas-build`**. You build; the architect
designs, reviews and merges. Felipe is the final authority on product/copy.

Working dir: **`/Users/fcavalcanti/dev/esp-atlas`** (NOT `~/code/esp-atlas`).

## Ground truth, in priority order
1. **`SPEC-INDEX.md`** — wins every conflict. Ownership map, glossary, collisions
   C1–C6, architecture ruling §4, open gaps G1–G7.
2. `SPEC.md` (governance/entities) · `INTERFACE-SPEC.md` (API/site/CLI/Groq).
3. `SPEC-wizard.md` (Flash Wizard) · `SPEC-home-explorer.md` (home IA, §2 layout
   locked @ b371851) · `SPEC-hosting-lane.md` · `SPEC-freshness.md` ·
   `SPEC-data-population.md` · `SPEC-discovery.md`.
4. `AGENTS.md` (record-authoring rules) · `PROJECT_KNOWLEDGE.md` (untracked, dated
   2026-08-22 — parts are stale, e.g. test counts).

**Read SPEC-INDEX.md first and confirm it in the room before writing code.**

## Non-negotiable rules
- **PR-only.** `main` is branch-protected. CI = `schema` + `tests` (pytest) +
  `sources-live`. **Humans merge** (the architect has Felipe's clearance to review
  and merge on green + spec-match). Never merge your own PR.
- **Cite-or-omit.** Every hard spec value carries a live `sources:` entry. Never
  guess. If you cannot verify it, omit the field and say why in the record body.
- **Verify, don't claim.** Run the validator, the suite, and the actual feature.
  Report real numbers. Felipe's standing instruction: *before saying something is
  ready, test it.*
- **Surface your judgment calls** instead of burying them. Put any
  "review-before-merge" ask at the **top** of the PR body and the room message —
  the architect reads top-down and merges fast on green.
- Conventional commits. Report continuously in the room. Blocked or the spec looks
  wrong? **Ask — don't guess.** (Two specs have already been wrong; see below.)
- **gh account flip**: `gh auth switch --user fcavalcantirj` before any PR/repo op,
  then back to `fcavalcanti-onvida`. Otherwise gh cannot even see the repo.
- **Secrets**: the Solvr room is **PUBLIC**. Never paste tokens or keys there or
  into any file. Ask Felipe for the room write-token. `GROQ_API_KEY` is env-only
  and is **already set in Vercel production**.

## Where things stand (verified at handover time)

**Merged to `main`:** `#34` generated-examples engine · `#35` §2 layout spec ·
`#36` firmware enrichment (recipe graph 19 → 54) · **`#37` intent-first home**
(merged during handover; deploying to prod — the old layout Felipe saw on the live
site was simply this PR still being open).

**Open, both CI-green and `CLEAN`, awaiting architect review:**
| PR | Branch | What |
|---|---|---|
| **#38** | `feat/ask-groq` | `POST /ask` + `/ask` page on verified Groq models; system prompt v2 |
| **#39** | `feat/flash-manifest-proxy` | `GET /manifest/<recipe>.json` + SSRF-guarded streaming `/flash-bin` proxy + 10 verified Launcher `bin_url`s |

⚠️ **Rebase #38 and #39 on the new `main`** before doing anything else — #37 moved
web files (`HomeView.tsx`, `ResultsPanel.tsx`, `lib/api.ts`, `SiteHeader.tsx`,
`app/sitemap.ts`). #38 touches `SiteHeader.tsx`/`sitemap.ts` and adds `/ask`, so a
small conflict is likely; #39 is backend-only and should be clean.

**Room:** the architect answered PR #37 (seq 18). Messages seq 15–17 — the P3 data
finding, the `serialType` spec bug, and the PR #39 report — were still unanswered at
handover. **Read from seq 15 and act on any rulings that landed since.**

## Verified facts — do NOT re-derive these
- **Groq models are account-specific.** ⚠️ `llama-3.3-70b-versatile` **404s on this
  account** despite being in Groq's public docs. `GET /v1/models` shows no Llama
  chat model at all. Pinned: **`openai/gpt-oss-120b`** (Ask) and
  **`openai/gpt-oss-20b`** (fast path). gpt-oss returns an extra `reasoning` field
  beside `content`; read `content`. Verify against `/v1/models`, never the docs.
- **GitHub release assets send no `access-control-allow-origin`.** The same-origin
  streaming proxy is *required*, not optional. Launcher hit the identical wall and
  routes through `api.launcherhub.net/flasherProxy`.
- **Launcher binaries are merged images flashed at offset 0 for every chip family.**
  The per-chip difference is `0xFF` padding *inside* the file. Byte-verified through
  our proxy: classic ESP32 = `ffffffff` at 0x0 + bootloader magic at 0x1000; S3 =
  magic at 0x0 + app magic at 0x10000.
- **esp-web-tools 10.4.0 manifest contract** (from `src/const.ts` / `src/flash.ts`):
  `offset` must be a **JSON number** (esptool-js does arithmetic on it); `chipFamily`
  is exact string equality vs esptool-js `CHIP_NAME`; `"improv"` is NOT a real field;
  `new_install_skip_erase` is deprecated and inverts its own name.
- **Web Serial is Chromium-desktop only** (no Safari/Firefox/mobile) — confirmed
  with Felipe. Handle via the `unsupported` slot.
- Launcher asset names are PlatformIO env names, case-sensitive and inconsistently
  cased (`m5stack-cardputer`, `CYD-2432S028`, `Marauder-v4-OG`). **Do not normalize.**

## Open questions the architect owes you
1. **`serialType` spec amendment.** SPEC-wizard's P3 line is inverted: the tool
   detects cdc/uart itself from the port's VID/PID and uses `serialType` only to
   pick among several builds, falling back **only** to an `undefined` label. A lone
   labelled build therefore *breaks* flashing. #39 ships one unlabelled build.
2. **T-Display-S3**: Launcher 2.8.0 ships `-touch`/`-pro`/`-amoled` but no plain
   asset. Which serves the non-touch board? Left uncited on purpose.
3. **Erase default**: #39 sets `new_install_prompt_erase: true` so the human is
   asked before a wipe. Architect may prefer the silent-erase default.
4. **Ask is blind to the recipe graph.** "Which boards run Marauder?" returns
   "not in esp-atlas yet" because `firmware`/`recipe` are deliberately outside the
   `parts` table and FTS index. Widening `ask()` retrieval crosses a boundary the
   architect owns — do not do it unilaterally.
5. **G4** intent→filters JSON contract · **G1/G2/G5** entities (`prompt-recipe`,
   `example`, firmware `tags[]`) · **L3** click-analytics storage (recommendation on
   record: GA4/edge capture + re-rank baked at build, keeping the site static).

## Mistakes already made — do not repeat
- **Do not propose a `download_mode` schema field.** Felipe was emphatic: *every ESP
  can be plugged in via USB and flashed*; esptool-js drives the DTR/RTS auto-reset.
  Holding BOOT is a recovery edge case. Framing it as a P2b blocker was wrong.
- **Always use absolute paths when writing files.** A relative write from the wrong
  cwd clobbered `apps/web/.env.example` (restored from git).
- **Backticks in shell heredocs get interpreted.** Write commit messages and room
  posts via a quoted-delimiter python heredoc (`<<'PYEOF'`) or a temp file.
- Don't announce a spec is "buildable" without checking the data exists — P3 was
  specced as decided-and-buildable, yet **0 of 54 recipes had a `bin_url`**.
- ⚠️ **A hand-resolved CSS conflict is invisible to the entire CI gate.** Resolving
  a `globals.css` conflict by naively keeping both sides spliced two blocks
  mid-rule, leaving `.intent-prompt {` unclosed and the file three braces
  unbalanced — and `tsc`, eslint, `next build` and 274 tests **all passed**, because
  none of them parse CSS. Only a screenshot caught it (a button had dropped below
  its input). After any CSS merge: check `{` vs `}` counts, confirm each selector
  appears once, and **screenshot the affected pages before pushing**.
- `sources-live` is `continue-on-error: true` and GitHub sometimes **429s the CI
  runner**. A red there is not automatically a dead link — fetch the URL yourself
  before editing any record.

## Immediate next task — P2b: the flash UI (SPEC-wizard P2b)
The backend landed in #39; the button does not exist yet. **#39 should merge first.**

Build, per `SPEC-wizard.md` "The Flash Wizard" + P2b:
- A flash action on **board pages** (`/parts/[id]`) and **firmware pages**
  (`/firmware/[id]`), grouped by trust tier — `RecipeGroupList.tsx` and
  `TrustTierBadge.tsx` already exist and render the recipe graph (P2a shipped).
- **Consent gate**: checkbox wired to ESP Web Tools' `activate` slot, carrying the
  spec's disclaimer verbatim (asserts the link at the shown tier; can brick/erase).
- **Branch on `recipe.flash.method`**: `release-bin` → `<esp-web-install-button>`
  pointed at `/api/manifest/<recipe-id>.json`; a **404 from that endpoint means fall
  back to guided handoff** (that is the designed signal). `m5burner` / `web-flasher`
  → guided handoff deep-link.
- **`unsupported` slot** → Chromium-desktop-only message. Pin the loader to
  `esp-web-tools@10` (currently 10.4.0).
- Progress bar from `state-changed`
  (`initializing → manifest → preparing → erasing → writing → finished | error`),
  surfacing the device's own error text.

**Spike first if unsure** — this is the one area with no test coverage (there are no
web tests, by design; enforceable invariants live in core/api pytest). A throwaway
static page driving the real endpoint against real hardware is the honest way to
validate before wiring it into the app. **Felipe owns the hardware test** — ask him
to flash a real device before you call P2b done.

## Roadmap after P2b
M2 remainder (`GET /index.json`, then **G4** intent→filters behind the existing home
prompt) → **F1–F5** freshness cron (F1 = link-liveness sweep reusing
`scripts/check_sources_live.py`; F4 detects boards but **hands authoring to
population**, per C2) → **population** pack → **discovery** pack (needs G1/G2) → **L3**.

Lead already banked for F3: Launcher's `WebPage` branch publishes `flasher.json`, a
per-release `device → binary` catalog — machine-readable recipe-drift input.

## Environment
```bash
cd /Users/fcavalcanti/dev/esp-atlas && git pull            # start of every session
python3 -m venv <scratchpad>/venv                          # your own scratchpad
<venv>/bin/pip install -e "apps/core[test]" -e "apps/api[test]" -e "apps/cli[test]"
```
- **Kill before starting anything** (Felipe's standing rule):
  `lsof -ti:8010 -ti:3000 | xargs kill -9`
- API: `<venv>/bin/python -m uvicorn esp_atlas_api.main:app --port 8010`
  (**8010, not 8000** — Docker occupies 8000 locally).
- Web: `cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8010 npm run dev`.
- Screenshots that worked: headless Chrome
  `--headless --disable-gpu --hide-scrollbars --window-size=1440,1250 --screenshot=<out> --virtual-time-budget=6000 <url>`.
- After switching branches run `npx next typegen` **before** `npx tsc --noEmit`
  (stale `.next/dev/types` produces phantom missing-module errors; `rm -rf .next/dev/types` clears it).

## Verification — the gate before every PR
```bash
python3 scripts/validate.py                                   # expect N/N valid, 0 errors
<venv>/bin/python -m pytest apps/core/tests apps/api/tests apps/cli/tests -q
cd apps/web && npx next typegen && npx tsc --noEmit && npx eslint . && npm run build
```
Then **exercise the actual feature** (boot API + web, click it, screenshot it) and
quote real numbers in the PR. Baselines at handover: `validate.py` **170/170**;
pytest **288** on `feat/flash-manifest-proxy` (counts differ per branch).
For flash work specifically, prove bytes end-to-end:
`curl -s -r 0-3 "http://localhost:8010/flash-bin?recipe=m5cardputer__launcher" | xxd`
→ must be `e903023f` (`0xE9` = ESP image magic).

## Your first moves
1. `git pull`; read `SPEC-INDEX.md`, then `SPEC-wizard.md` (P2b/P3).
2. Get the room token from Felipe → `solvr room-join esp-atlas-build --token <…>`
   (the skill needs `SOLVR_ROOM_TOKEN` exported, or `--token`).
3. Read the room from seq 15 for the architect's answers to the open questions.
4. Post: SPEC-INDEX confirmed, you have the handover, you are starting P2b, and ask
   for a ruling on anything above that blocks you.
5. **Validate this handover against the repo before building.** If something here
   contradicts the code, the code wins — and say so in the room.
