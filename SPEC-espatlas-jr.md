# SPEC — EspAtlas Jr. 🤖 (the data keeper)

> Status: **CONVERGED — building.** (All interview `⟨Q⟩`s resolved 2026-08-27; harness = **Agno**
> on Groq free `gpt-oss-120b` — see §8a.) `⟨Q…⟩` markers are kept as a resolved-decision log,
> each prefixed **RESOLVED**. `fx-open` is permanently out of scope (§0/§9).
> **This spec converges and REPLACES the four data-lane specs** — `SPEC-freshness.md`,
> `SPEC-data-population.md`, `SPEC-discovery.md`, `SPEC-data-maintainer.md` — keeping
> the good of each, nothing duplicated. Those become historical once this lands.

## 0. The one hard separation (do not blur again)

esp-atlas is two fully-decoupled systems:

| | 🔍 **Home Search** (read) | 🤖 **EspAtlas Jr.** (write) |
|---|---|---|
| Does | answers user queries over retrieved records | keeps the atlas fresh + growing |
| Data | **reads part** of the atlas | **writes** the whole atlas (via cited PRs) |
| LLM | **Groq** (always improving) | **lean free model** (Groq free `gpt-oss-120b`) + deterministic guard |
| Owner | `INTERFACE-SPEC.md` | **this spec** |

The only coupling is one-way: **Jr writes the atlas; Home Search reads it.** Jr never
touches Groq or search; Home Search never fetches or writes data. `fx` is **ditched** —
not Jr's runtime, not mentioned again.

## 1. What Jr is

Jr's purpose is one sentence: **keep 100% of esp-atlas verified and verifiable — at
scale and over time.**

**Jr's body is a LEAN, provider-agnostic coding agent — NOT the full DasBrowCoder
stack.** **RESOLVED (2026-08-27): the body is `Agno` 3.x** (Python, model-agnostic, native
Groq) on Groq free `gpt-oss-120b`, tested 3/3 live on the Pi (see §8a). Chosen because it
ships Jr's two hardest requirements natively — **persistent memory** (§8) and the **e2e/
health/trigger server** (§7) — while staying lean and Python (Felipe's turf). Still bolted on:
the guard→PR tool, crons, and the Telegram notify path. *(smolagents runner-up; `fx-open`
permanently rejected — see §0/§9. Not to be reintroduced.)*

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
| **Issue/Discussion/bug watch** | daily-cheap | firmware repos' GitHub **Issues + Discussions**; **our own** esp-atlas Issues/Discussions | upstream compat-break/new-device/bug → recipe-drift PR, trust demotion, or our Issue; **user-reported bad data on our repo → correction PR** |
| **Recipe / compat drift** | daily (highest volatility) | firmware repos vs recipes (`User_Setup`, `#define`, release `.bin` names, README device lists) | recipe PR / Issue |
| **Pin & io refresh** | periodic | re-verify `gpio_pins`/`reserved_pins`/`power_out` against the cited pinout/datasheet | corrected io PR (the motto's *over-time* guarantee) |
| **Board population** | weekly, vendor-batched | Arduino `package_*_index.json` + `boards.txt`, Launcher devices, vendor spec pages | new `board`/`module`/`soc` records |
| **Manufacturer watch** | daily-cheap | Espressif products/datasheets/HW-guidelines, M5Stack docs, M5Burner | **new `soc`/`module`/`board`/`brand` the day a vendor posts it**; datasheet-revision `io`/spec PRs |
| **launcherhub backlog-drain** | staleness queue | launcherhub `giveMeTheList` (hundreds, mostly uncatalogued) | drain into `unverified` firmware + valid recipe; dedup vs catalogued; rank by **REAL** GitHub stars |
| **Community discovery** | periodic | awesome-esp32, HN, GitHub-trending, **r/esp32 (`score > 50` only)** | firmware / `example` candidates, **with-code gated** |
| **Brand/vendor upkeep** | monthly | vendor homepages (per `brand`) | brand liveness/redirects; **auto-create `brand`** on a newly-seen vendor |
| **Seed self-expansion** | as-found | Jr's own discovery output | propose new `seeds.json` entries (new firmware repo / vendor / list) via one-file PR |
| **Growth telemetry** | **weekly** | GA4 Data API + Search Console API (`esp-atlas.com`) | **consolidated performance digest → Telegram/webhook**; GSC top-demand queries → data-priority signal (§3d) |

**RESOLVED ⟨Q2⟩ — hybrid cadence.** The high-drift, cheap jobs run on a fixed daily
tick: **liveness · firmware-releases · recipe-drift**. The expensive jobs —
**board-population · community-discovery · pin&io-refresh** — run off a single
**staleness queue** (oldest-`verified` record wins each tick) within the daily budget.
Fixed cadence for what drifts fast and cheaply; staleness queue for what's expensive and
slow-moving.

**RESOLVED ⟨Q3⟩ — liveness is privileged.** When the budget is tight, **liveness always
runs first** (it is what keeps the motto true); every other job competes by staleness for
the remaining budget.

### 3a. Full responsibility map (every entity has an owner — no orphans)

Jr's job is `keep 100% verified & verifiable — at scale, over time`, applied to **all 7
entities** across four verbs. Every cell below is owned by a job above; if a cell is empty,
that's a coverage hole to close, not a silent gap.

| Entity | DISCOVER (find new) | POPULATE (author) | VERIFY (keep true) | PRUNE (dead) |
|---|---|---|---|---|
| **soc** | Manufacturer watch (Espressif) | Manufacturer watch | Pin&io refresh + datasheet-drift | Liveness |
| **module** | Manufacturer watch (Espressif/vendor module datasheets) | Manufacturer watch | datasheet-drift (flash/psram/antenna/certs) | Liveness |
| **board** | Board population + Manufacturer watch + Community discovery | Board population | Pin&io refresh | Liveness |
| **brand** | auto-create on new vendor | Brand/vendor upkeep | Brand upkeep (monthly homepage liveness/redirect) | Liveness |
| **firmware** | Community discovery + **launcherhub drain** | releases + launcherhub drain | version-drift + **Issue/Discussion/bug watch** | Liveness |
| **recipe** | Board population + launcherhub drain | recipe authoring | **Recipe/compat drift** + **Issue/Discussion watch** (compat breaks) | orphan-check (guard) |
| **example** *(⚠ not real yet — no dir/schema; create in v1)* | Community discovery ("what people built") | Community discovery, `unverified` | staleness re-check | Liveness |
| **companion** *(⚠ stub — `.gitkeep` only, no schema)* | ⟨Q10⟩ | ⟨Q10⟩ | ⟨Q10⟩ | ⟨Q10⟩ |

> **Entity reality check (verified 2026-08-27):** 6 schemas exist (board·brand·firmware·module·
> soc·recipe) + 7 data dirs (those + `companions`). **`companions` is a stub** (no schema) and
> **`example` does not exist** (aspirational). v1 scope decision: **create the `example` entity**
> (dir + schema) since Community discovery + Home Search both need it; **defer `companion`** (⟨Q10⟩).

### 3b. Named source rules (the specifics, resolved)

- **r/esp32 (`reddit-esp32` seed):** poll `r/esp32.json`; **admit only posts with `score > 50`**
  (Felipe's bar — signal over noise). Extract repo/firmware/board mentions from the post +
  top comments; **with-code gate** (must resolve to a real public repo or release `.bin`);
  dedup vs catalogued; auto-author `unverified` or open an Issue if it needs judgment.
- **THE LAUNCHER CATALOG = the primary firmware source, drained FIRST.** The Launcher's
  catalog page (`bmorcelli.github.io/Launcher/catalog.html`) is JS-rendered off
  **`api.launcherhub.net/giveMeTheList`**, which returns **2,487 firmware entries** (verified
  2026-08-27) vs. our **16** catalogued — this is the real firmware backlog. Each entry carries
  `fid, name, description, category, tags, author, **github**, download, versions`. Strategy:
  - **Drain this backlog before any other firmware discovery.** Each tick take the top-N
    not-already-catalogued, ranked by **REAL GitHub stars** (fetch via the `github` field — the
    API's own `star`/like count is a near-zero internal counter, **never use it**; `download`
    is a fair secondary popularity signal). Skip forks/mirrors (e.g. `bmorcelli/esp32marauder`
    ≈ Marauder). Author `unverified` firmware + a valid recipe against a catalogued board.
  - **Persist a `seen/drained` ledger over all 2,487 `fid`s** so the backlog monotonically
    shrinks, nothing is re-proposed, and new upstream additions are detected on re-fetch.
  - Second firmware source in the same family: **M5Burner API** (`m5burner-api.m5stack.com`,
    live) for the M5Stack ecosystem.
  - **Only after the launcher backlog is drained** do the long-tail sources (below) matter for
    *new* firmware — they catch what never made it into the Launcher catalog.
- **Manufacturer watch (Espressif, M5Stack, …):** the `espressif-products` /
  `-datasheets` / `-hw-design-guidelines` and `m5stack-docs` / `m5burner` seeds are watched
  **daily-cheap** for *new parts* — a new ESP32 variant, module, or dev board should become a
  cited `unverified` record the day it's posted (this is how Jr catches parts past my training
  cutoff — the `esp32-s31` lesson). Datasheet **revisions** trigger `io`/spec re-verify PRs.
- **Issues / Discussions / bugs (new source class):** watch two surfaces via the GitHub API
  (official, rate-limited — no scraping):
  1. **Upstream** — each catalogued firmware repo's `/issues` + `/discussions`. Signal to mine:
     *compat breaks* ("Bruce v2.x bricks Cardputer") → recipe-drift PR or a **trust-demotion PR**
     (human-merged — Jr never sets `trust_tier` itself, per §6);
     *new-device support* → recipe/firmware candidate; *recurring bug* → note on the record or
     our Issue. Filter by reactions/engagement to stay above noise (mirror the `score > 50` spirit).
  2. **Our own** esp-atlas `/issues` + `/discussions` — **a user reporting bad/stale data is a
     first-class correction trigger**: Jr reads it, verifies against the cited source, and opens a
     **fix PR** (or replies asking for specifics). Framed as a *polled job*, so it does **not**
     add a 4th inbound channel — §7's "exactly three inbound" stays intact.
- **Firmware coverage (a firmware is not "done" at one recipe):** when Jr adds or maintains a
  firmware, it authors a recipe for **every catalogued board the repo says it supports** — not
  just the first. Boards the firmware supports but that aren't catalogued yet are omitted
  (cite-or-omit) and can seed a board-population candidate. A firmware whose page lists only one
  board when the repo names several is a **coverage gap** Jr should close (e.g. Evil-M5Project →
  Cardputer + AtomS3 + Core2). Runs as part of authoring and as a periodic re-check of catalogued
  firmware against newly-added boards.
- **Seed self-expansion:** when discovery surfaces a productive new firmware repo, vendor, or
  list not in `seeds.json`, Jr proposes adding it (one-file PR) — the seed set grows itself.

⟨Q10 — **`companion` entity** (1 record today): is it in Jr v1 scope (which source seeds it,
what cadence), or deferred like `prompt-recipe`? My lean: **defer** — no seed feeds it and its
purpose is thin; revisit when a real companion-data need appears.⟩

⟨Q11 — **Reddit ingest depth:** post-title + selftext + top-N comments, or title/link only?
My lean: title + selftext + top ~10 comments (that's where the repo links live), still
`score > 50` gated.⟩

### 3c. Firmware discovery — priority order (the part that needed improvement)

Firmware is Jr's weakest-covered entity today (16 records). Ordered pipeline:

1. **Launcher catalog** (`giveMeTheList`, 2,487) — **drain first**, real-star ranked (§3b).
2. **M5Burner API** — M5Stack ecosystem firmware.
3. **Release-tracking** — the 11 `firmware_releases` seeds, for version drift on what's catalogued.
4. **Long-tail discovery** (only for what's *not* in 1–2) — GOOD places for genuinely new firmware:
   `awesome-esp` lists · **r/esp32 `score > 50`** · GitHub trending `topic:esp32` · HN · Issues/
   Discussions of catalogued repos (new-project mentions) · ⟨Q13⟩ **PlatformIO / ESP Component
   Registry** as additional catalogs?

**RESOLVED ⟨Q12⟩ — expand Manufacturer watch to ALL major ESP32 board makers** (verified
reachable 2026-08-27): **Espressif · M5Stack · LilyGO · Heltec · Seeed (XIAO) · DFRobot ·
Waveshare · Adafruit**. Prefer each vendor's **machine-readable Arduino package index** where
it exists (Adafruit ships `package_adafruit_index.json` — gold; Espressif already seeded),
else the vendor product/wiki page. Each is one `board_catalogs`/vendor-spec seed.

**RESOLVED ⟨Q13⟩ — add both registries** as firmware/library catalog seeds: **PlatformIO
Registry** (`api.registry.platformio.org`) and **ESP Component Registry**
(`components.espressif.com/api`). Both live; exact query params are an implementation detail.

### 3d. Growth telemetry & the 1,000,000-user north-star

North-star: **1MM users on `esp-atlas.com`.** You can't steer there blind — so Jr consolidates
the site's analytics and reports weekly. **This stays inside Jr's nature: MEASURE + STEER-DATA +
REPORT. It is NOT marketing** — launch/visibility/experiments/monetisation are Felipe's call
(*propose, do not implement* — the SEO-handover governance rule).

**Wiring (verified, already provisioned):** GA4 property `properties/551132215` (GCP project
`esp-atlas-ga4`), Search Console `sc-domain:esp-atlas.com`, read via the service account
`esp-atlas-ga4-admin@esp-atlas-ga4.iam.gserviceaccount.com` (**read-only**; key minted-on-request
and revoked after — a secret, never in the repo). APIs: `analyticsdata` + `searchconsole`
(+ `pagespeedonline` optional). The 2026-08-22 SEO audit already pulled both via this SA — the
path is proven.

**Weekly digest (Jr → Telegram/webhook), consolidated GA4 + GSC:**
- **Users / traffic**: active users, new users, sessions, week-over-week Δ, and **progress toward 1MM**.
- **Acquisition**: top channels, top landing pages, top countries.
- **Search (GSC)**: total clicks/impressions/CTR/avg-position Δ; **top queries**; **rising queries**;
  **high-impression / low-CTR pages** (title/desc opportunities); indexed-coverage changes.
- **Health**: Core Web Vitals / PSI trend; 404s (feeds the liveness/NotFound signal).

**The steering loop (this is why it's Jr's, not a bystander's):** GSC **demand** is a first-class
**data-priority signal** — queries with impressions but no matching record, or a thin one, jump
the staleness/population queue. *People are searching for a board/firmware we don't cover well →
Jr prioritizes authoring/deepening it.* Analytics thus steers **which data Jr keeps**, closing the
loop between what users want and what the atlas provides — without Jr ever touching growth levers.

**RESOLVED ⟨Q14⟩ — Jr hosts the telemetry cron + digest** (its crons + §7 outbound + the
data-priority tie-in make it the natural home), under the hard boundary above: measure / report /
steer-data only — never a growth lever.

**RESOLVED ⟨Q15⟩ — both outputs**: a **weekly Telegram summary** AND a committed
`docs/telemetry/<date>.md` snapshot (git-tracked history, so trends are auditable).
**1MM target date: 2026-11-27** (3 months from 2026-08-27, set by Felipe) — the digest reports
required weekly-active-user growth pace vs. this deadline.

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

**RESOLVED ⟨Q4⟩ — auto-author when it's cheap to reject.** For a firmware whose repo/`.bin`
resolves to a real public artifact, Jr **auto-authors an `unverified` record** (a bad one
just gets rejected — cheap). When the claim needs hardware/compat human judgment, Jr opens
an **Issue only**, never a record.

**RESOLVED ⟨Q5⟩ — keep `example`, defer `prompt-recipe`.** The `example` entity ("what
people built", surfaced by Home Search) stays. `prompt-recipe` is **deferred** — not in
Jr v1's scope; revisit only if a real need shows up.

## 6. Trust promotion

`unverified → trusted` (or a compat/trust-tier claim) is done by a **human editing
`trust_tier` in a normal PR** through the same guard — git-tracked, auditable, no separate
system. Jr may *surface a promotion candidate* (an Issue "these 6 have been live 30 days,
promote?") but never sets the tier itself. **RESOLVED ⟨Q6⟩ — mechanism accepted as-is.**

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

- **Model: RESOLVED (2026-08-27) → Groq free `openai/gpt-oss-120b` is the PRIMARY lane.**
  Proven reliable live (5/5 HTTP 200 under sequential load; seconds/call). **Free Laguna 2.1 S
  (`poolside/laguna-s-2.1:free`, $0, 262K ctx) WORKS but is per-minute rate-limited**: a single
  spaced call is clean (200, "OK"), and smolagents' one-shot passes with backoff — but a
  multi-step agent loop crawls (every call re-hits the RPM cap → backoff; a file round-trip took
  ~4 min and still flaked). So Laguna free = fine for single/low-freq calls, **too slow/flaky for
  Jr's multi-step authoring loop** unless a **BYOK Poolside key** (own rate limits) or **paid
  Laguna** ($0.09/1M) is used. Groq free is the fast/reliable loop lane; Laguna is the secondary.
  Free-tier trains on I/O — a non-issue because **Jr only touches public atlas data**.
- **Harness: RESOLVED (2026-08-27) → `Agno` 3.x** (Python, model-agnostic; native `Groq`
  model class). Chosen over smolagents because it **ships the two things Jr needs that smol
  makes you hand-build** — §8 persistent memory and the §7 e2e/health/trigger surface — while
  running the same free Groq loop. **Tested 3/3 live on the Pi**: (a) multi-step tool loop on
  Groq `gpt-oss-120b` (`ALPHA-AGN`); (b) **persistent memory across a fresh process** — a
  second agent recalled a stored vendor quirk *"use the compact product-page pinout… Hookup
  Guide pages exceed the buffer"* from `SqliteDb`; (c) **AgentOS FastAPI serve** — 88 endpoints
  incl. `/health` (the health ping) and `POST /agents/{id}/runs` (the on-demand trigger).
  Python + Groq-native + Felipe's turf. *(smolagents was runner-up; fx-open permanently
  rejected — §0/§9. Do not reintroduce fx-open.)*
- **What Agno gives natively vs. what we still add:** Agno provides the loop, tools,
  **persistent memory (`SqliteDb`)**, and the **AgentOS server** (§7's health + trigger
  endpoints). We still add: the **crons** (systemd timers on the Pi), the **guard→PR tool**
  (shell → `validate.py`/`check_sources_live.py` → `gh` PR), and the **Telegram** notify path.
- **Cost is bounded structurally:** free Groq model = ~$0 for authoring; the free req cap
  *is* the natural rate-limit. Premium delegate stays available for the rare hard record,
  but the default lane is free.
- **RESOLVED ⟨Q8b⟩ — hard daily cap ≤ 10 PRs/day** (on top of the provider's free req cap),
  so human review stays humane; excess authored records queue to the next day.

## 11. Open questions (consolidated)
- **RESOLVED ⟨Q1b⟩ — harness = `Agno` 3.x** (Python; tested 3/3 on the Pi — loop, persistent
  memory, AgentOS serve; see §8a). smolagents was runner-up.
- **RESOLVED ⟨Q8b⟩ — ≤ 10 PRs/day** (see §8a).
- **RESOLVED ⟨Q9⟩ — B/C-series deferred.** Jr v1 owns the A-series live-data lanes (§3).
  B/C-series (`gpio_pins` pin-planner, schematic images) is a later phase, not v1 scope.
- **RESOLVED ⟨Q1 host⟩ — Jr is its own always-on instance** on a dedicated low-spec box
  (the aarch64 Pi it was tested on is the natural home), separate `box.env` / identity /
  GitHub bot token from the main DasBrowCoder. Exact host is a deploy detail, not a spec one.

### Remaining real-world TODOs (not spec decisions — deploy/ops)
- **Model lane**: Groq free `gpt-oss-120b` is the proven default. Laguna-via-OpenRouter stays
  parked until a BYOK Poolside key (private rate limits) makes the free pool usable in a loop.
- **Secrets**: keys live at `~/.config/jr/keys.env` (mode 600, non-repo). Deploy reads from there.

*Resolved: Q1 (own instance on the Pi) · Q1b (harness = smolagents, tested) · Q2/Q3 (hybrid
cadence + liveness-privileged) · Q4 (auto-author cheap, Issue for judgment) · Q5 (keep
`example`, defer `prompt-recipe`) · Q6 (trust-promotion mechanism) · Q7 (3 inbound hooks,
Felipe-only) · Q8 (Groq free `gpt-oss-120b` primary; Laguna deferred, throttled) · Q8b (≤10 PRs/day)
· Q9 (B/C-series deferred) · Q10 (defer companion) · Q11 (Reddit title+selftext+top-10, score>50)
· Q12 (all 8 makers) · Q13 (PlatformIO + ESP Component registries) · **Q1b (harness = Agno)**.*
