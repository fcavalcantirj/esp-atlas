# esp-atlas — project spec

## Vision
A single, verifiable, machine-queryable, community-owned knowledge base covering the
**entire ESP32 family** (SoCs), the modules built on them, and the dev boards from
every vendor — with a query layer that answers "which ESP for X?" and only answers
what the data supports.

## Why it exists
Existing ESP guides are POV-locked (maker vs IoT vs security), unversioned (frozen at
publish date), unverifiable (specs with no datasheet cite), and un-queryable (prose,
not data). esp-atlas fixes all four: open data, git-versioned, source-cited, queryable.

## Core principle — separate knowledge from interface
```
CONTENT (git repo)          →  BUILD/INDEX     →  INTERFACE (site)
structured markdown,            schema-validated   wizard · chat · compare
community PRs, datasheet-cited   + index.json      rendered FROM the repo
```
The repo is the single source of truth. The site is a pure function of it. See
ARCHITECTURE.md.

## Data model
Three inherited layers so specs are declared once:
- **soc** — the silicon (`data/socs/<id>/chip.md`)
- **module** — SoC + flash/PSRAM/antenna in a can (`data/modules/<id>/module.md`)
- **board** — module + USB/regulator/headers/peripherals, by brand (`data/boards/<brand>/<id>/board.md`)

Frontmatter = queryable YAML (validated by `schema/`); prose = human context. Every
hard spec carries a `sources:` entry. Fields not verified are omitted, never guessed.

**brand** — editorial identity for a `data/boards/<id>/` vendor folder
(`data/brands/<id>/brand.md`), one per brand: display `name`, homepage `url`,
`sources`. It is *not* a part: never indexed into the queryable parts table,
never a `/search` or `/wizard` result. It exists purely so the site can render
"LILYGO" instead of the raw folder slug `lilygo`; a folder with no `brand.md`
yet just falls back to rendering its slug. Populated for every vendor folder
currently under `data/boards/`. Every part record the core/API return also
carries `brand_name`/`brand_url`, resolved from this lookup — the raw slug
(`vendor_or_brand`) stays on the record for filtering and URLs, but no
user-facing label anywhere on the site (part pages, result cards, page
titles, OG images, JSON-LD, brand browse chips) renders it directly.

**Board memory (`flash_mb`/`psram_mb`):** most boards don't reference a `module`
record — they state flash/PSRAM as free-text in `notes:` instead, which made memory
unqueryable. `schema/board.schema.json` mirrors the module schema's optional
`flash_mb`/`psram_mb` numeric fields directly on `board`, so a board can carry a
structured memory size without requiring a `module` link. Like every hard spec, a
value is set only when the board's own notes/source state it explicitly — never
inferred from chip/board name (e.g. "ESP32-S3" does not imply 8 MB PSRAM).
`psram_mb: 0` means the source explicitly says no PSRAM; the field is omitted
entirely when PSRAM is simply not mentioned. For a module-linked board, the value
comes from the linked module's resolved flash/PSRAM unless the board's own notes
state a different, more specific variant.

**Exception — `price_tier`:** boards may optionally carry `price_tier:
cheap|medium|expensive`, an **approximate, editorial** street-price bucket,
set by hand and never cited to a `sources:` entry. It powers the wizard's
`budget` filter only — it is not a spec, never presented as one, and always
visibly separate from the verified fields above it.

## Interface (three views, one backend)
1. **Wizard** — "what are you building?" → band/protocol/smart-home mesh
   (802.15.4: Thread/Zigbee/Matter)/power/form-factor/budget → filter structured
   data → ranked boards, each with the reason it won.
2. **Ask (chat)** — natural language → retrieve matching records → Groq answers,
   grounded + cited, "not in esp-atlas yet" when unknown. Temperature 0.
3. **Compare / part pages** — auto-generated from the repo.

## Tech
- Site: Next.js, static-generate part pages from markdown; deploy on Vercel.
- Query artifact: `scripts/build_index.py` → `index.json`, published by CI, fetched live.
- Chat: Groq free tier (LLM inference; no embeddings → no vector DB in v0). Key via
  `GROQ_API_KEY` env only.
- Content: markdown + YAML. No database.

## Governance
- CI gate: `scripts/validate.py` (schema + source rule, plus the dataset-level
  no-orphan-firmware check — every `firmware` must have ≥1 `recipe`) on every PR.
- CODEOWNERS per brand folder (as boards grow).
- oracle-loop bot opens PRs for missing/stale parts; humans always merge. The daily
  freshness engine (link-liveness, firmware-release/recipe drift, board/brand
  discovery) is specced in `SPEC-freshness.md`. **(ROADMAP — not built as of 2026-08-30:
  no scheduled cron runs; only the sources-live CI check exists. Real agent work lives in
  `jr/` / `SPEC-espatlas-jr.md`.)**
- License: data CC-BY-SA 4.0, code MIT.

## Phasing
- **v0 (done):** repo + schema + CI + validator + index builder + 12 datasheet-verified SoCs.
- **v1:** module & board schemas; seed ~30 popular boards; the static site (compare + part pages).
- **v2:** wizard + Groq chat (shipped). *oracle-loop bot: ROADMAP, not running.*
- **v3:** full board coverage; companions (nRF24/CC1101/LTE-GNSS); public launch.
- **v4:** Flash Wizard + community recipes (`firmware`/`recipe` content types, "what
  runs on what", in-browser flashing via ESP Web Tools) — see `SPEC-wizard.md`.
  **P1 shipped:** schemas + validation wiring + a 6-firmware/19-recipe hand-cited
  seed + core accessors (no flashing UI yet). CI enforces **no orphan firmware**:
  `scripts/validate.py` fails if any seeded firmware has zero referencing recipes.

## Anti-goals
Not a shop / not affiliate bait · not tutorials (link out) · not a forum · not a
wholesale datasheet mirror (cite, don't copy).
