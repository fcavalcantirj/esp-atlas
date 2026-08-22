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
- CI gate: `scripts/validate.py` (schema + source rule) on every PR.
- CODEOWNERS per brand folder (as boards grow).
- oracle-loop bot opens PRs for missing/stale parts; humans always merge.
- License: data CC-BY-SA 4.0, code MIT.

## Phasing
- **v0 (done):** repo + schema + CI + validator + index builder + 11 datasheet-verified SoCs.
- **v1:** module & board schemas; seed ~30 popular boards; the static site (compare + part pages).
- **v2:** wizard + Groq chat; oracle-loop bot live.
- **v3:** full board coverage; companions (nRF24/CC1101/LTE-GNSS); public launch.

## Anti-goals
Not a shop / not affiliate bait · not tutorials (link out) · not a forum · not a
wholesale datasheet mirror (cite, don't copy).
