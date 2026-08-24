# SPEC-INDEX — canonical ownership map, glossary & collision resolutions

> **On any conflict between specs, THIS document wins.** It exists so a builder
> agent never gets contradictory instructions. Every other spec defers here for
> ownership boundaries and vocabulary.

## 1. Ownership map (exclusive scope per spec)
| Spec | Owns |
|---|---|
| `SPEC.md` | Governance root: vision, entity model (soc/module/board + brand), memory fields, `price_tier`, CI gate + no-orphan rule, phasing. |
| `INTERFACE-SPEC.md` | Runtime: API endpoints, Next.js site, CLI, FTS5 retrieval, **all** Groq calls/guardrails. |
| `SPEC-wizard.md` | **Flash Wizard**: firmware/recipe entities, trust tiers, ESP Web Tools, manifest, `serialType`, CORS/flash bridge. |
| `SPEC-freshness.md` | **The oracle-loop runtime** (the single cron) + the *maintenance* adapter pack (liveness, release/recipe drift). |
| `SPEC-data-population.md` | The *official-catalog seeding* adapter pack (new boards/modules/socs from Arduino index, Launcher, M5Burner). |
| `SPEC-discovery.md` | The *community-discovery* adapter pack (awesome-esp32, GitHub trending, Reddit, HN) **+ the `prompt-recipe` and `example` entities**. |
| `SPEC-home-explorer.md` | Home IA: 3 sections, Newcomer Wizard (classic→Groq), and **surfacing/ordering** of examples. Consumes, never defines, the cron. |
| `SPEC-hosting-lane.md` | The **server-capable memory lane**: `psram_min`/`flash_min` filters + oracle invariants. (UI naming/placement per §3 here.) |

## 2. Canonical glossary (fixed names — use these, nothing else)
- **Board Wizard** — the deterministic board-picker (`SPEC.md`/`INTERFACE-SPEC.md`).
- **Flash Wizard** — the flash-a-binary flow (`SPEC-wizard.md`).
- **Newcomer Wizard** — the easy intent prompt on the home (`SPEC-home-explorer.md`).
- **the oracle-loop** — the ONE scheduled cron, run by `SPEC-freshness.md`, with three
  **adapter packs** (maintenance / official-seeding / community-discovery). No other
  spec defines a separate job — they register adapters into it.
- **server-capable** — a board with the PSRAM/flash headroom to run a web server
  (`SPEC-hosting-lane.md`). **Do NOT call this "hosting."**
- **rehost / host a binary** — serving firmware `.bin` files (`SPEC-wizard.md` anti-goal).
- **site hosting** — Vercel deployment (`INTERFACE-SPEC.md`).
- **examples** — the home §3 clickable suggestions (the ONE term; not "chips",
  "presets", or "shelves"). Distinct from `hosting-lane`'s "active-filter chip".

## 3. Collision resolutions (from the coherence audit)
- **C1 — cron fragmentation.** `freshness` is the single cron runtime; `population`
  and `discovery` are **adapter packs** registered into it, not separate jobs.
  `home-explorer` §5 must **reference** discovery, not re-describe the cron.
- **C2 — board discovery specced twice.** New-part **authoring** belongs to
  `population`. `freshness` F4 only **detects** new-board candidates and hands them
  off; drop its "new-part PRs" wording.
- **C3 — examples ownership.** `discovery` **authors** the `example` entity;
  `home-explorer` only **surfaces/orders** it. Fix `home-explorer` §3b to cite
  discovery (not "population/freshness cron") as the source.
- **C4 — memory UI placement.** The intent-phrased **"Runs a web server / heavy app"
  toggle is a top-level control**; the raw `psram_min`/`flash_min` MB dropdowns live
  in **Advanced**. The toggle is exempt from home-explorer's "memory→Advanced" rule.
- **C5 — "hosting" overloaded.** Rename the concept to **server-capable** (see §2);
  reserve host/rehost for binaries and Vercel only. (`SPEC-hosting-lane.md` filename
  kept for git history; its concept is "server-capable memory lane".)
- **C6 — Groq has two jobs.** (a) *Ask* = RAG answer over retrieved records
  (`INTERFACE-SPEC.md`, cache `hash(question+index_version)`). (b) *Intent-parse* =
  query→structured filters (`home-explorer`, cache by query string, no retrieval,
  index-version-independent). Both are **owned by `INTERFACE-SPEC.md`** — add the
  intent-parse call there as a named endpoint.

## 4. Cross-cutting architecture ruling (repo-is-truth vs "alive")
The "alive/self-feeding" vision must not silently break the static model:
- **Content** (firmware / `prompt-recipe` / `example`) = **git records via PR**.
  Repo-is-truth holds; the site stays a static function of the repo. ✅
- **Trend scores** are **baked into records** at ingest/refresh by the oracle-loop.
  Static holds. ✅
- **⚠ Global click-analytics ranking** (home-explorer §3b/§5, discovery §6) is the
  ONE thing that needs runtime event capture — it conflicts with SPEC.md's
  "no database, read-only static". **DECISION REQUIRED** before L3 (options: edge
  analytics + periodic re-rank baked at build · client-side only · a small managed
  store for analytics alone). Does not block L1/L2.

## 5. Gaps to close before a builder implements (owner in brackets)
- **G1 `prompt-recipe` entity** [discovery] — needs `schema/prompt-recipe.schema.json`,
  a SPEC.md entity-model entry, `validate.py` `SCHEMAS` wiring, and an API endpoint.
- **G2 `example` entity** [discovery] — frontmatter, `data/examples/` folder or
  saved-query form, schema, render contract undefined.
- **G3 click-analytics storage** [INTERFACE-SPEC] — see §4 ⚠; unspecified store.
- **G4 Groq intent→filters JSON contract** [INTERFACE-SPEC] — model + schema (home-explorer §11).
- **G5 firmware `tags`** [SPEC-wizard] — home-explorer §7 wants multi-tag
  (`games`,`dev-tool`,…); wizard has single-enum `category`. Reconcile to a `tags[]`.
- **G6 recipe path is stale doc** [SPEC-wizard] — says flat file
  `data/recipes/<board>__<firmware>.md`; actual layout is a **folder**. Fix the text.
- **G7 no-dead-intent oracle** [hosting-lane pattern] — extend the dead-ends oracle to
  cover example/prompt-recipe chips (every surfaced chip → ≥1 result).

## 6. Minor
- Schema `$id` domain drift: `schema/*.json` use `esp.wiki`; INTERFACE-SPEC fixes
  `esp-atlas.com`. Pick one canonical domain.
- Record-level `verified_at`/`verified_by` vs source-level `verified` share a stem
  but are distinct — leave as-is, documented here.
