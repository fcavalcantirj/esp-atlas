# Interface Spec — esp-atlas web + agent

Locked design for the interaction layer. Build follows the milestones below.
Companion to `SPEC.md` (the project) and `ARCHITECTURE.md` (the data layer).

## Decision: C — both, layered
One brain, many shells. The **agent-core** (retrieval + grounded answer) is built once;
the **website**, **CLI**, **MCP tool**, and any bot are thin front-ends over it.

Confirmed choices:
- **Surfaces:** website **and** agent (CLI + API), layered.
- **Site scope:** **wizard + ask**, nothing bloated. Part pages/compare are the browsable
  substrate; wizard + ask are the interaction.
- **Stack:** **Next.js** frontend · **Python (FastAPI)** backend (reuses our Python
  tooling + best LLM ecosystem; Go was the alternative, not chosen).
- **Hosting:** Vercel (frontend). Backend as Vercel Python functions to start; can move
  to a small always-on container (Fly/Railway) if the FTS index wants persistence.
- **Domain:** `esp-atlas.com` primary (broad/authoritative; makers + devs), grab
  `esp-atlas.dev` as alias. *(Felipe registers — needs his account/payment.)*
- **Repo:** monorepo, `data/` kept pristine.
- **Visibility:** private until we decide to launch.
- **LLM:** Groq free tier; models pinned at build, with response-header rate-limit
  handling + answer caching. **`openai/gpt-oss-120b`** for *Ask* (the quality
  path) and **`openai/gpt-oss-20b`** for the cheap/fast path (intent→filters).
  Both 131K context, both verified live on the project key 2026-08-24. The model
  roster is **account-specific**: verify against `GET /v1/models` before changing
  these, not against Groq's public model list — the previously specced
  Llama-70B-class model (`llama-3.3-70b-versatile`) returns 404 on this account.

## Retrieval — scalable, because we map *everything*

The dataset grows to thousands (all SoCs + modules + boards + companions). So retrieval
is a real layer, not context-stuffing:

```
data/**/*.md ──build_index.py──▶ index.json  (compact frontmatter, for the site)
                              └─▶ esp-atlas.db (SQLite FTS5: structured + full-text)

query ─▶ structured filter (radio/band/protocol/form) + FTS (name/prose/notes)
      ─▶ top-K records ─▶ Groq (temp 0, prompts/system.md) ─▶ grounded + cited answer
```

- **SQLite FTS5** — zero external infra, scales to 100k+ rows, does structured `WHERE`
  and `MATCH` in one. The pragmatic default.
- **Not zvec** — that's our private agent memory, not a public backend.
- **Embeddings/vector** — added later *only if* keyword recall proves insufficient
  (a `sqlite-vec` column, not a new service).
- **Chat scales** because only top-K records enter the prompt, never the whole dataset.

## Two interaction modes
1. **Wizard** — deterministic filter over the index. No LLM, no key, no cost, un-abusable.
   Guided questions (band? protocol? form factor? budget?) → ranked parts + why each won.
   `budget` (cheap/medium/expensive) is a spending ceiling against each board's
   optional, editorial `price_tier` — never a hard spec, see `SPEC.md`.
   The site's Wizard UI asks a single plain-language `ieee802154` yes/no
   ("smart-home mesh — Thread / Zigbee / Matter") instead of the three-way
   `protocol` picker, since all three share the same C6/H2-only radio; `needs.
   ieee802154=true` returns only parts with the 802.15.4 radio present (ESP32-C6/
   H2 and boards built on them). `protocol` stays a valid `/wizard` need for
   API/power-user callers that want to filter by the specific mesh protocol a
   part advertises support for. `radio` (and `/search?radio=`) is a **minimum**
   Wi-Fi generation, not an exact match — Wi-Fi generations are backward
   compatible, so `radio=wifi-4` also matches wifi-6 parts (e.g. ESP32-C6/C5),
   while `radio=wifi-6` matches only wifi-6 parts. Parts with no Wi-Fi radio at
   all (e.g. ESP32-H2) never match a `radio=` request.
2. **Ask** — natural language → RAG-lite → Groq → grounded, cited, temp 0,
   "not in esp-atlas yet" when unknown. Robust: retrieval + grounding + caching + rate limits.

## Components & contracts

**agent-core** (Python lib, backend-internal)
`ask(question) -> {answer, citations:[{part, file, source_url}], used:[ids]}`
`search(query, filters) -> [records]`

**API** (FastAPI)
- `POST /ask {question}` → grounded answer + citations
- `GET  /search?q=&radio=&protocol=&form=&brand=` → structured+FTS results
- `POST /wizard {needs}` → deterministic ranked parts
- `GET  /facets` → distinct values + counts per filterable column, for building UI
  dropdowns from the data. `vendor_or_brand` entries are `{value, count,
  display_name, url}` — `display_name`/`url` resolved from `data/brands/<value>/
  brand.md` (falling back to the slug when no such record exists); every other
  facet key stays a plain `{value, count}` list.
- `GET  /brands/{slug}` → `{brand: {slug, name, url}, results: [record...]}` — the
  brand's own editorial identity (same fallback-to-slug rule as above) plus every
  part with that `vendor_or_brand`. An unknown slug still returns 200 with
  `results: []`, never a 404 — the site 404s on the empty list itself.
- Every part record (from `/search`, `/wizard`, `/parts/{id}` and its `chain`/
  `related`, and `/brands/{slug}.results`) carries `vendor_or_brand` (the
  canonical folder slug, unchanged — used for filtering and `/brands/<slug>`
  URLs) alongside `brand_name` (the editorial display name, resolved from
  `data/brands/<slug>/brand.md`, falling back to the slug) and `brand_url`
  (the brand's homepage, or `null` when unknown). The site renders `brand_name`
  wherever a brand is shown to a human; `vendor_or_brand` is for hrefs/filters
  only, never a label.
- `GET  /index.json` → static passthrough
- `GET  /firmware` → every seeded firmware record (see `SPEC-wizard.md`). First-class
  like brand: never in `/search`/`/wizard`, never in `index.json` or the `parts` table.
- `GET  /firmware/{id}` → one firmware record, 404 if unknown.
- `GET  /recipes?board=&firmware=` → recipe records (the board x firmware edge),
  optionally filtered by `board` or `firmware` id; no params returns every recipe.
  Same first-class-entity rule as `firmware`. `chip_family` always equals the
  referenced board's `soc`; `board`/`firmware` refs are guaranteed to resolve
  (CI-enforced, see `esp_atlas_core.validate._check_inheritance`).

**Site** (Next.js, SSG)
- `/` home: wizard + ask box
- `/ask` full chat
- `/socs /modules /boards`, per-part page (frontmatter→rendered + sources), `/compare`
- Chat calls `/ask`; browser NEVER sees the Groq key (server-side only).

**CLI** (`esp-atlas`, wraps agent-core)
`esp-atlas ask "…"` · `esp-atlas search …` · `esp-atlas wizard`

## Collaboration — humans and agents
- **PR flow** (humans): existing CONTRIBUTING.md + CI schema/source gate.
- **`esp-atlas` skill** (agents): documents the schema/format, and mandates
  **search-before-add** (via `/search` or CLI) to dedup, then emit schema-valid
  markdown, then open a PR. Makes agent collaboration first-class.
- **oracle-loop** bot: same flow, scheduled, opens PRs for missing/stale parts.

## Monorepo layout (target)
```
data/            # the dataset — pristine, the crown jewel
schema/          # JSON Schema contracts
scripts/         # validate.py, build_index.py (Python)
apps/
  web/           # Next.js frontend
  api/           # FastAPI backend (agent-core + search + ask)
  cli/           # esp-atlas CLI
skills/
  esp-atlas/     # the contributor-agent skill
prompts/         # system.md (chat), etc.
```
`data/`, `schema/`, `scripts/` stay where they are; apps are added around them.

## Milestones
- **M0 — agent-core + CLI** (Groq-backed): talk to it in a terminal. The reusable brain.
- **M1 — static site: wizard + browse/compare** (no LLM, no key): the public face.
- **M2 — `/ask` API + chat box on the site**: full NL, grounded, rate-limited, cached.
- **M3 (optional) — MCP server + Telegram bot + oracle-loop bot live.**

Each milestone is usable alone; the brain is never built twice.

## Groq guardrails
Read `x-ratelimit-*` response headers; backoff on 429; cache answers by
`hash(question + index_version)`; the deterministic wizard has no LLM cost and stays
available if the free tier is exhausted.
