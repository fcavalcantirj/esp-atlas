# SPEC — discovery engine (community/social signal → cited content)

> Status: DRAFT. The **third face of the cron.** `SPEC-freshness.md` keeps records
> live; `SPEC-data-population.md` seeds boards from official catalogs; **discovery**
> harvests the *cool, trending* ESP32 world — new firmware, projects-with-code,
> prompt recipes — from community/social sources and turns it into cited, human-
> merged content. Same detect→propose→gate machinery. Nothing hand-authored.

## 1. Principle
The home's alive examples, the "cool firmware," and the prompt recipes are **not a
maintained list** — they are outputs of a continuous engine watching real signal.
It can't go stale because it *is* the feed. But it stays honest: everything is
cited, code-backed, and human-merged — never a bot inventing hype.

## 2. Sources (adapters) — official APIs only, no scraping
| Source | API / feed | Yields |
|---|---|---|
| **awesome-esp32** lists | GitHub raw + repo API | curated firmware/projects firehose |
| **GitHub trending + releases** | GitHub Search/Releases API | new & rising firmware, projects-with-code |
| **Reddit r/esp32** | Reddit API (OAuth, rate-limited) | trending posts **that link a repo** |
| **Hacker News** | HN Firebase API | ESP32 stories **that link a repo** |

Rate-limit-aware, read-only. **No ToS-violating scraping** (inherited from freshness).

## 3. The hard gate: "with code"
A candidate is admissible **only if it resolves to a real, public repo** (or a
release `.bin`). No repo → dropped. This is what separates a prompt recipe / cool-
firmware entry from linkbait: every surfaced item is grounded in runnable code.

## 4. Outputs (what discovery authors)
1. **firmware** candidate → the existing firmware/recipe flow (owned by wizard/freshness).
2. **prompt-recipe** → a new entity (below).
3. **example** → an alive chip for the home §3 (a saved query or a link to (1)/(2)).

### The `prompt-recipe` entity (prompt-only, model-free)
```
id: esp32s3-wifi-webserver          # slug
type: prompt-recipe
title: "ESP32-S3 Wi-Fi web server with a REST endpoint"
goal: "Serve a small REST API + status page over Wi-Fi"
target:                              # optional links into the atlas
  soc: esp32-s3
  capability: [wifi, psram_min>=2]
prompt: |                            # THE payload — copy-paste, model-agnostic
  Build a PlatformIO project for an ESP32-S3 that ...
usage: "Paste into any coding agent."   # generic, NEVER names a model/CLI
origin:                              # attribution + provenance
  repo: https://github.com/.../...
  discovered_via: reddit|hn|awesome|github-trending
sources:
- field: '*'
  url: <the repo/post>
  verified: '2026-08-24'
status: unverified                   # trust-tier promotion is human-only
```
- **No model, no provider, no CLI version** — the prompt is the durable asset; those
  drift and would rot the record.
- The only thing that ages is the ESP32 API the prompt references (slow) — freshness
  watches the origin repo for liveness.

## 5. Pipeline (detect → propose → gate → surface)
1. **Detect** — adapters pull candidates; **dedup** by repo URL / id (idempotent).
2. **Gate: with-code** — drop anything without a resolvable repo/bin.
3. **Author** — an agent writes the record (firmware / prompt-recipe / example),
   **cite + attribute** the origin, schema-valid, `status: unverified`.
4. **Propose** — one **PR**, labeled (`discovery:firmware`, `discovery:prompt`,
   `discovery:example`); idempotent (update, never duplicate).
5. **Gate** — existing CI (schema + sources-live + oracle) + **human merges.**
6. **Surface** — ordered by **trend signal (stars/upvotes/recency) + click-analytics**.
   Every "trending/new" badge cites source + timestamp. **No faked trending.**

## 6. Honesty rails (non-negotiable, inherited)
1. With-code or it doesn't enter.
2. Cite + attribute the original author/repo — we point and surface, never claim.
3. Official APIs, rate-limited, no scraping.
4. `status: unverified` on ingest; trust promotion **human-only, forever**.
5. Bot proposes, humans dispose — never writes `main`.

## 7. Relationship to the other specs
- **freshness** re-checks liveness of what discovery ingested (origin repos drift).
- **population** seeds boards from *official* catalogs; discovery seeds *community*
  content (firmware/prompts/examples). Complementary, same rails.
- **home-explorer** consumes it: the alive §3 examples and the prompt-recipe /
  firmware pages are discovery's surface.

## 8. Open questions
- Trend-score formula (how to weight stars vs upvotes vs recency vs clicks).
- Prompt-recipe review depth before merge (a human should sanity-run at least once?).
- Volume controls — cap discovery PRs/day so review stays humane.
