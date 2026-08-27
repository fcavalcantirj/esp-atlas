# SPEC — EspAtlas Jr. 🤖 (the data keeper)

> Status: DRAFT (interview in progress — `⟨Q…⟩` marks a pending Felipe decision).
> **This spec converges and REPLACES the four data-lane specs** — `SPEC-freshness.md`,
> `SPEC-data-population.md`, `SPEC-discovery.md`, `SPEC-data-maintainer.md` — keeping
> the good of each, nothing duplicated. Those become historical once this lands.

## 0. The one hard separation (do not blur again)

esp-atlas is two fully-decoupled systems:

| | 🔍 **Home Search** (read) | 🤖 **EspAtlas Jr.** (write) |
|---|---|---|
| Does | answers user queries over retrieved records | keeps the atlas fresh + growing |
| Data | **reads part** of the atlas | **writes** the whole atlas (via cited PRs) |
| LLM | **Groq** (always improving) | Claude (agent) + deterministic guard |
| Owner | `INTERFACE-SPEC.md` | **this spec** |

The only coupling is one-way: **Jr writes the atlas; Home Search reads it.** Jr never
touches Groq or search; Home Search never fetches or writes data. `fx` is **ditched** —
not Jr's runtime, not mentioned again.

## 1. What Jr is

Jr's purpose is one sentence: **keep 100% of esp-atlas verified and verifiable — at
scale and over time.**

**Jr's body is a LEAN, provider-agnostic coding agent — NOT necessarily the full
DasBrowCoder stack.** Candidates (research-open): **Kimi Code CLI** (MIT, TypeScript,
provider-configurable, subagents — lacks Telegram, addable), **picoclaw**, or another
lean tweakable harness. Runs on a **free/cheap model** (see §8). Whatever the harness,
he needs: the guard→PR pipeline, memory, browser/fetch, crons, and the 4 inbound hooks.

### 1a. Why a cheap/free model is SAFE (the structural unlock)

Jr's verifiability guarantee lives in the **deterministic guard + human-merge, NOT the
model.** A weak model that hallucinates a spec is **blocked** — `sources-live`/schema/
oracle fail — and a human merges regardless. The worst a cheap model does is *waste a
PR that gets rejected*. So the motto is protected by the pipeline, and Jr's authoring
model can be as lean as we like. This is what makes a free OpenRouter/Groq model viable.

From the harness he needs:
- **The delegate → guard → merge pipeline** — he authors records, a *deterministic*
  guard (zero-LLM) gates them, he opens a **cited PR**; a **human merges**. (The exact
  flow proven across this whole session.)
- **Semantic + working memory** — remembers rejected proposals, vendor quirks (e.g.
  *"SparkFun hookup pages overflow the buffer → use the compact product-page pinout"*,
  *"M5 docs state 'IO ×N + pin list'"*), and what's going stale.
- **Skills** — his own reusable procedures (a `board-authoring` skill, a `pin-derive`
  skill, a `liveness-sweep` skill…).
- **Watchers / channels** — Telegram + webhook for notifications, alerts, and support/e2e.
- **Crons** — MANY scheduled jobs (below), not one daily tick.
- **Browser/fetch tools** — he navigates official sources himself.

⟨Q1 — Jr runs as a **separate agent instance on its own box**, distinct from the main
DasBrowCoder (you), right? Same `dasbrow-hermes-coder` stack, different `box.env` /
identity / GitHub bot token. Which host — a Pi, a Hetzner box, brownet?⟩

## 2. Non-negotiable contract (the settled invariants, from all four specs)

1. **Motto:** every hard spec quoted-and-cited or derived-with-math-shown-and-inputs-cited. Never from memory. (`CLAUDE.md`.)
2. **Cite-or-omit**, per field, right owner. `validate.py` + `check_sources_live.py` gate it.
3. **Bot proposes, humans dispose.** Jr **never writes `main`** — only PRs (and Issues for hardware judgment).
4. **Auto = `unverified`.** Trust-tier promotion is **human-only, forever.**
5. **Official APIs, rate-limited, no ToS-violating scraping.**
6. **Deterministic guard** (schema + sources-live + oracle/no-orphan) blocks every PR that fails; Jr cannot override it.

## 3. Jr's jobs (the crons)

Each job is the same anatomy — **pick seeds → navigate → compare with current data →
propose cited PR** — differing only in source and cadence. Seeds live in `seeds.json`.

| Job | Cadence⟨Q2⟩ | Source | Proposes |
|---|---|---|---|
| **Liveness sweep** | daily | HTTP-check every `sources[].url` | dead-source PR/Issue + freshness age |
| **Firmware releases** | daily | GitHub Releases per firmware | version-drift PR |
| **Recipe / compat drift** | daily (highest volatility) | firmware repos vs recipes (`User_Setup`, `#define`, release `.bin` names, README device lists) | recipe PR / Issue |
| **Pin & io refresh** | periodic | re-verify `gpio_pins`/`reserved_pins`/`power_out` against the cited pinout/datasheet | corrected io PR (the motto's *over-time* guarantee) |
| **Board population** | weekly, vendor-batched | Arduino `package_*_index.json` + `boards.txt`, Launcher devices, vendor spec pages | new `board`/`module`/`soc` records |
| **Community discovery** | periodic | seeds: awesome-esp32, HN, Reddit, GitHub-trending, **launcherhub** | firmware / `example` candidates, **with-code gated** |

⟨Q2 — cadence: keep this daily/weekly split, or a single staleness-driven queue (oldest
`verified` record wins each tick)? My lean: liveness/releases/recipe daily (cheap,
high-drift); population/discovery/pin-refresh on a **staleness queue** within a budget.⟩

⟨Q3 — priority when budget is tight: **liveness always runs** (keeps the motto true);
the rest compete by staleness. Agree?⟩

## 4. Anatomy of one job (the loop)

1. **Pick seeds** — from `seeds.json` for that job (Jr can also *propose* new seeds via PR).
2. **Navigate** — fetch the official source (browser/API), buffer-safe (compact source,
   one page at a time — a memorised lesson).
3. **Compare with current data** — diff the source against the atlas record: new part?
   changed spec? dead link? drifted recipe?
4. **Author** — write/patch the record, **cite-or-omit**, **verify each value against the
   source** (not memory), math shown for derived values.
5. **Guard** — deterministic pipeline (schema + sources-live + oracle). Red guard blocks.
6. **Propose** — one focused **PR** (or Issue if it needs a human/hardware judgment).
7. **Notify** — Telegram/webhook: "PR #N proposed", "dead source", "needs your eyes".
8. **Remember** — record the outcome in memory (avoid re-proposing a rejected item;
   store the vendor quirk learned).

## 5. Discovery specifics (the with-code gate)

Admissible only if it resolves to a **real public repo** (or release `.bin`). The
**launcherhub** adapter is the gate's clearest case:
- **parse** `giveMeTheList` → `{fid,name,github,category,esp}`;
- **dedup** against catalogued firmware (skip forks/mirrors, e.g. `bmorcelli/esp32marauder` ≈ Marauder);
- **rank by REAL GitHub stars** (the API's `star` field is a near-zero internal like-count — do NOT use it);
- author the top-N not-already-catalogued as `unverified` firmware + a valid recipe against a catalogued board.

⟨Q4 — auto-author vs flag: **auto-author `unverified`** for a firmware with a resolvable
repo (cheap to reject), **Issue-only** when a hardware/compat claim needs human judgment. Agree?⟩

⟨Q5 — entity scope: keep the **`example`** entity ("what people built", surfaced by Home
Search) and **cut/defer `prompt-recipe`**? Or keep both?⟩

## 6. Trust promotion

`unverified → trusted` (or a compat/trust-tier claim) is done by a **human editing
`trust_tier` in a normal PR** through the same guard — git-tracked, auditable, no separate
system. Jr may *surface a promotion candidate* (an Issue "these 6 have been live 30 days,
promote?") but never sets the tier itself. ⟨Q6 — this mechanism OK?⟩

## 7. Channels & support (the webhook / e2e ask)

Jr is reachable and reaches out:
- **Outbound:** Telegram/webhook on every proposed PR, dead-source alert, needs-judgment Issue, and a periodic freshness digest.
- **Inbound (Felipe, resolved):** exactly three, and they're minimal (not bespoke
  "channels" — gitmerge + health are things most agents already have):
  1. **On-demand via channel** — a Telegram command (e.g. *"Jr, refresh the M5 boards"*)
     triggers a job now. **Authorised: Felipe only** (his chat id).
  2. **Git-merge webhook** — GitHub fires on merge so Jr learns what got accepted
     (updates memory, clears the staleness item, never re-proposes it).
  3. **Health / e2e ping** — a liveness endpoint so we know Jr is alive and his last
     run's status.
  No other inbound surface. Telegram is the one human channel; the other two are plumbing.

## 8. Memory (what Jr keeps)

- **Rejections** — never re-propose a human-rejected record.
- **Vendor quirks** — the buffer-safe sourcing lessons, per-vendor pinout patterns.
- **Staleness ledger** — oldest-`verified` records, to drive the queue.
- **Seed health** — which seeds are productive vs noisy.
Working memory is box-local (never shipped), per the DasBrowCoder memory law.

## 9. What Jr is NOT
Not Home Search (no Groq, no answering users). Not the merger (humans merge). Not the
validator/guard (deterministic, separate). Not the site. Not `fx`.

## 10. Migration
On acceptance: fold the good of `SPEC-freshness / -data-population / -discovery /
-data-maintainer` into this file, update `SPEC-INDEX.md` ownership (one row replaces four),
and leave a one-line tombstone in each old spec pointing here.

## 8a. Runtime & model (Felipe, resolved — free-first, research-open)

- **Model:** free-tier first. **Start: Poolside Laguna (via OpenRouter)** — `laguna-s-2.1`
  (118B-A8B, 70% Terminal-Bench, free 256K ctx, 200 req/day) or the leaner `laguna-xs-2.1`
  (33B). Fallback / second lane: **Groq free tier**. Free-tier trains on I/O — a non-issue
  because **Jr only touches public atlas data**.
- **Harness:** research-open, lean + tweakable preferred — **Kimi Code CLI** (MIT/TS,
  provider-configurable → point at OpenRouter) or **picoclaw**. Low memory footprint.
- **Cost is bounded structurally:** free model = ~$0 for authoring; the 200 req/day free
  cap *is* the natural rate-limit. Premium delegate stays available for the rare hard
  record, but the default lane is free. ⟨Q8b — a hard per-day request/PR cap on top of
  the free-tier limit, so review stays humane? e.g. ≤ N PRs/day.⟩

## 11. Open questions (consolidated)
- ⟨Q1b — pick the harness: **Kimi Code CLI** vs **picoclaw** vs other. I can spike both
  lean-first (memory footprint, OpenRouter wiring, how hard the 3 inbound hooks are).⟩
- ⟨Q8b — daily PR/request cap (above).⟩
- ⟨Q9 — does Jr also own **B/C-series data** (pin-planner `gpio_pins`, schematic images)
  as recurring jobs once shipped, or is that one-off human-triggered work?⟩

*Resolved: Q1 (lean provider-agnostic body, not full DasBrowCoder) · Q2/Q3 (leans) ·
Q4/Q5/Q6 (leans) · Q7 (3 inbound: on-demand-via-Telegram + gitmerge webhook + health
ping, Felipe-only) · Q8 (free model, Laguna-via-OpenRouter first).*
