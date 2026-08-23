# esp-atlas — Freshness / daily oracle-loop spec

> Extends `SPEC.md` governance ("oracle-loop bot opens PRs for missing/stale parts;
> humans always merge") into a continuous, automated freshness engine. Companion to
> `SPEC-wizard.md`, whose `recipe` records are the most volatile data of all.

## The problem, honestly stated
Everything drifts, at wildly different rates. A `verified: 2026-08-22` cite is a
**claim about the past**. Without continuous re-checking, esp-atlas slowly becomes a
confident museum. Freshness must be automated **and** still cited + human-merged —
never a bot silently rewriting truth.

## What drifts, and how fast (this drives cadence)
| Data | Drift rate | Signal watched | Cadence |
|---|---|---|---|
| `sources` (every record) | — | HTTP liveness of each `sources.url` | daily |
| `firmware` releases | weekly | GitHub Releases API per firmware | daily |
| `recipe` / compat matrix | **highest** | firmware repo (envs, `User_Setup`, `#define`, release `.bin` names, README device lists) + latest release vs recipe `firmware_version` | daily |
| `board` | monthly | vendor sitemaps/product pages, Launcher catalog, M5Burner API | weekly |
| `brand` | rare | vendor homepage liveness/redirects | monthly |
| `soc` | rare | Espressif product/datasheet pages | monthly |

## Principles (inherited, non-negotiable)
1. **Bot proposes, humans dispose.** The job **never writes `main`** — it opens PRs and Issues.
2. **Cite or omit.** Every proposed change carries a source URL. The bot cannot invent a spec or a compatibility claim.
3. **Auto-harvested recipes land `status: unverified`.** Trust-tier promotion is **human-only, forever.**
4. **Make staleness visible, not just fixed.**

## The daily job — four stages
1. **Detect** — per-source *adapter*, read-only, rate-limit-aware, prefers official
   **APIs / sitemaps / release feeds** over scraping (no ToS-violating scraping).
2. **Diff** — detected state vs repo → changeset `{new, changed, stale, dead}`.
3. **Propose**
   - Cited + schema-fillable → **PR**, labeled (`new-board`, `firmware-release`, `recipe-drift`, `dead-source`…).
   - Needs human judgment / hardware → **Issue** (e.g. "Marauder v0.x may have dropped StickC Plus2").
   - **Idempotent** — update the existing PR/Issue; never duplicate.
4. **Gate** — the existing CI (`schema` + `sources-live` + `tests`) runs on the bot PR; a human reviews and merges.

## Staleness as a first-class, visible signal
- Derive a **freshness age** per record from `sources.verified`.
- Recipes pin `firmware_version` → if a firmware's latest release ≠ the pinned
  version, mark the recipe **stale**: display a greyed/lower tier and open a
  re-verify Issue.
- The site *shows* it: "verified 2026-08-22", "⚠ source last checked 94d ago",
  "recipe may be outdated for v6".
- A **`/freshness` dashboard**: % of sources checked in 7/30d, dead-source count,
  # recipes lagging latest firmware, board-coverage vs a target list. A public
  trust signal and the bot's own scoreboard.

## Infra — no new servers
- **GitHub Actions `schedule:` cron** (the repo already runs on GHA); a bot token
  opens PRs/Issues via the API.
- **Tiered lanes:** daily (links, firmware releases, recipe drift) · weekly (board
  discovery) · monthly (full re-verify + soc/brand sweep).
- Concurrency-guarded (one run at a time); resumable via a small per-adapter state
  file so it never re-proposes what is already open.

## Noise control (or reviewers drown)
- Classify **confirmed** (dead link, moved page, release exists) vs **heuristic**
  (age-based "possibly outdated"). Only *confirmed* becomes a PR; *heuristic* is a
  dashboard flag, not a PR.
- Cap proposals per day; dedup; every proposal is one-click-verifiable via its evidence link.

## Anti-goals (extends SPEC.md)
Never auto-merge · never fabricate a spec · never auto-promote a trust tier · no
binary rehosting · no ToS-violating scraping. The bot **drafts and surfaces; humans
decide.**

## Phasing (smallest-highest-signal first)
- **F1** — daily link-liveness sweep → dead-source PRs/Issues + freshness age on
  records. Reuses `scripts/check_sources_live.py`; tiny, immediate value.
- **F2** — firmware-release watcher → recipe-drift Issues (version lag).
- **F3** — recipe harvesters (per-project adapters) → `unverified` recipe PRs.
- **F4** — board/brand discovery (vendor sitemaps, Launcher catalog, M5Burner API) → new-part PRs.
- **F5** — `/freshness` dashboard.
