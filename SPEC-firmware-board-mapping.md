# SPEC — Firmware→board mapping: correctness, provenance, coverage

Status: DRAFT (for review). Author: session 2026-09-21.
Supersedes the narrower "boards/ manifest extractor" idea — that is now one source
among several.

## 0. Why (the finding that triggered this)

Felipe spot-checked two firmware; both were wrong the same way:

- **esp-claw** (`espressif/esp-claw`): upstream declares **39 boards** in an authoritative
  `application/edge_agent/boards/<vendor>/<board>/` manifest tree (incl. ESP32-P4 and
  ESP32-C5 boards). esp-atlas maps **1** (`m5stick-s3`), SoC `[esp32-s3]` only, name
  "For StickS3". The mapping is a **stale 2026-08-27 genesis seed**.
- **evil-m5project** (`7h30th3r0n3/Evil-M5Project`): upstream README "🧱 M5Stack Devices"
  table lists Cardputer, Core2, Fire, Core1, AWS, CoreS3, CoreS3 SE, AtomS3, StickC
  v1.1/v2, + Evil-M5Core3/Evil-Face variants. esp-atlas maps **3** (atoms3, cardputer,
  core2) — also **stale genesis seeds**.

Both `signals.json` show `resolved.boards: []`, `signals: []` — Jr's automated board
grounding **recovered nothing**, so each survives on its partial genesis seed.

### Systemic measurement (this is the real answer to "how do we know they're mapped right?")
Across the catalog (measured 2026-09-21):
- **63 / 106 firmware (59%) have `resolved.boards: []`** — zero extracted board signals.
- **0 / 224 recipes are `status: verified`** — every firmware→board edge is `unverified`.
- Many multi-board firmware map to 1–3 boards (18 firmware have a single recipe).

**Conclusion: we do NOT know firmware→board mappings are correct, and the majority are
under-mapped stale seeds.** This spec makes board coverage *extracted, sourced, and
measurable* instead of hand-seeded and frozen.

## 1. Current state (verified in source)
- Firmware records: `data/firmware/<id>/firmware.md` (frontmatter: socs, popularity, …)
  + `signals.json` (grounding run output: `resolved.boards/socs`, `signals[]`).
- Recipes (the firmware→board edges): `data/recipes/<board>__<firmware>/recipe.md`
  (`board`, `firmware`, `status`, `chip_family`, `sources`). Served via
  `core_recipes_for_firmware` → `/recipes?firmware=<id>` → the "Runs on N boards" UI.
- The board-signal extractor works for **43/106** firmware (e.g. draftling=8,
  openmqttgateway=6) — so it parses SOME README patterns — but returns empty for the
  other 59%. It does **not** read: (a) a repo `boards/`/`variants/` manifest tree
  (esp-claw), (b) structured README device tables/HTML (evil-m5project),
  (c) `platformio.ini` build envs, (d) per-board release/flasher manifests.
  (Note: `jr/board_backfill.py:434` reads a `boards/` dir, but for the *hardware
  catalog*, not firmware recipes — different path; do not conflate.)

## 2. Goal
1. Extract supported boards from the sources firmware actually use (multi-source).
2. Resolve them to esp-atlas catalog board ids; surface (never silently drop) the ones
   not in the catalog as candidate boards to add.
3. Attach provenance + a confidence/verification status to every recipe.
4. Make coverage auditable: know, per firmware, declared-vs-mapped, and catalog-wide the
   % of firmware with sourced board provenance.
5. Backfill the catalog behind a reviewed diff — never a blind mass write.

## 3. Board-source taxonomy (extract in this priority; a firmware may hit several)
1. **Manifest tree** — `boards/`, `variants/`, `targets/` dir with one entry per board
   (ESP-IDF / esp-claw style). Most authoritative. Enumerate leaf dirs; the vendor is
   the parent segment.
2. **`platformio.ini`** — `[env:*]` `board = ...` fields.
3. **README structured device list** — HTML `<table>` or markdown table/bullets under a
   "Supported / Compatible / Devices / Hardware" heading (evil-m5project style). Parse
   the device cells, not prose.
4. **Release / flasher manifest** — per-board `.bin` / ESP Web Tools `manifest.json`
   `builds[].chipFamily` + names.
5. **CI build matrix** — `.github/workflows/*.yml` board/target matrix.

Each extracted item keeps its **source URL + source type** for provenance.

## 4. Resolution (dir/table name → catalog board id)
- Extend `jr/board_alias.py` / `jr/device_map.py` with a normalized resolver:
  vendor + board slug → esp-atlas board id. Handles the naming gulf
  (`m5stack_sticks3` → `m5stick-s3`, `esp32_S3_DevKitC_1` → `esp32-s3-devkitc-1`,
  `xiao_esp32s3_sense` → `xiao-esp32s3`).
- **Resolve to a BOARD, never to a SoC.** (A quick fuzzy pass during this analysis wrongly
  collapsed several board dirs onto `esp32-s3`/`esp32-p4` — the resolver MUST reject
  SoC-level matches and demand a board, else it fabricates edges.)
- Unresolved names → a **candidate-boards report** (vendor, name, source, count of
  firmware referencing it), ranked — this is a growth lever for the board catalog, not an
  error to swallow. Do NOT invent a recipe for a board not in the catalog.
- SoCs: union the resolved boards' chip families into `firmware.socs` (esp-claw gains
  esp32-p4, esp32-c5).

## 5. Provenance + verification ladder
Each recipe gains explicit status:
- `seed` — genesis hand-seed, no repo source (today's 224 are effectively this,
  mislabelled `unverified`).
- `declared` — a repo source (manifest/table/pio/CI) names this board. Carries
  `source_url` + `source_type`.
- `verified` — a build/flasher manifest proves a flashable artifact exists for it.
Define "verified" = a per-board release asset or web-flasher build entry. `status`
never downgrades a human-verified edge.

## 6. THE ORACLE (per house rule + "how do we know") — write FIRST, RED
A golden fixture set of firmware with **hand-verified** expected board lists, spanning
every source type and both directions:
- esp-claw (manifest tree; ~39 declared; resolves to the N currently in catalog +
  a known candidate list) — pins under-extraction.
- evil-m5project (README device table; the ~10 devices) — pins table parsing.
- A platformio.ini repo, a flasher-manifest repo.
- **At least two firmware that genuinely support only 1 board** — pins the *opposite*
  failure (over-mapping / hallucinated edges). Correctness is two-sided.
The oracle asserts the extractor recovers exactly the expected resolved set (and the
expected unresolved-candidate set). This test is the thing that lets us *know*.

Plus a **catalog audit** (a Jr report / tick sub-step): per firmware, diff current
recipes vs freshly-extracted `declared` boards → flag `under-mapped`, `stale-seed`,
`unresolved-candidates`; emit a catalog metric `% firmware with ≥1 declared-sourced
board`. Baseline today ≈ 41% have any signal; target >90% for repos that declare boards.

## 7. Backfill (never a blind mass write)
- Run extraction across all 117 firmware → a **dry-run diff report**: per firmware, boards
  added/removed, socs changed, name corrections, unresolved candidates. No writes.
- Human-review the diff (board edges are the product's core claim; a wrong "Runs on"
  erodes trust). Then apply in batches, each landing as a normal tick PR through the
  existing guard.
- Re-verify a sample live (the `/recipes?firmware=` count matches the repo's declared set).

## 8. Honesty guarantees (non-negotiable)
- "Runs on N boards" counts only `declared`+`verified` edges; `seed`-only firmware are
  flagged internally as unproven until re-extracted.
- Every recipe shows provenance (source URL). No edge without a source once backfilled.
- The extractor prefers MISSING to WRONG: an unresolved board is a surfaced candidate,
  not a guessed mapping. (Golden rule: better a gap we can see than a false edge.)

## 9. Build sequence (phased; oracle → backend → audit → reviewed backfill)
- **P1** — Oracle + fixtures + the resolver (board_alias) with the SoC-rejection rule.
  RED→GREEN. No writes.
- **P2** — Source extractors, one at a time, each behind its own tests: manifest tree →
  platformio → README table → flasher manifest → CI matrix. (Divide & conquer; esp-claw
  drives P2a, evil-m5project drives P2c.)
- **P3** — Catalog audit report + coverage metric. Read-only.
- **P4** — Dry-run backfill diff over all 117; review; apply in reviewed tick batches;
  live re-verify.
- Each phase = one guard-gated delegate run, landed + verified.

## 10. Non-goals / risks
- Not building new board catalog entries automatically — unresolved names are *reported*
  for a human/Jr to add deliberately (adding boards is its own pipeline).
- Risk: aggressive table parsing invents edges → mitigated by the two-sided oracle
  (single-board fixtures) and the "reject SoC-level match" rule.
- Risk: repos restructure → provenance URLs rot → periodic re-extraction (tick already
  re-fetches signals).
