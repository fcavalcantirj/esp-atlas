# SPEC — EspAtlas Jr. 🤖 (the data keeper)

> Status: **CONVERGED — building.** (All interview `⟨Q⟩`s resolved 2026-08-27; harness = **Agno**
> on Groq free `gpt-oss-120b` — see §8a.) `⟨Q…⟩` markers are kept as a resolved-decision log,
> each prefixed **RESOLVED**. `fx-open` is permanently out of scope (§0/§9).
> **This spec converges and REPLACES the data-lane specs** — `SPEC-freshness.md`,
> `SPEC-data-population.md`, `SPEC-discovery.md` — keeping the good of each, nothing
> duplicated. Those become historical once this lands. (`SPEC-data-maintainer.md` was
> deleted 2026-08-30 — its dead fx-open design is superseded by this file.)

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
  - **Entries with no repo (G1b, 2026-11-03).** 1,229 entries carry `github: None` and ~20 an
    owner-only url (`https://github.com/geo-tp`). `jr/launcher_resolve.py` resolves them
    deterministically: ONE counted `gh api search/repositories?q=<significant name tokens>
    user:<owner>` (owner = the owner-only url's owner, else the entry `author` normalized to a
    GitHub login; no owner → no search, inconclusive — an unscoped search could hand the entry
    a stranger's repo). Accepted only when EXACTLY ONE hit's repo name shares a significant name
    token; the accepted repo then goes through the normal scorer and popularity floor
    unchanged (the floor stays the only admission gate). Zero or several matches → recorded
    once as `rejected` / `no_source_repo` with the unresolved TTL (7 d), keyed
    `launcher-<fid>` (repo `launcher:<fid>`), so it is not re-searched hourly. A search GitHub
    refuses with its "listed users ... do not exist" 422 (the `author` is a display name, not a
    login) is `owner_missing`, recorded with the archived TTL (90 d): the owner's absence does not
    change from week to week (2026-11-17: 213 entries, 146 authors, re-searched weekly for a month). A resolved entry
    leaves a `seen` note under the same key (`resolved: owner/repo`) once its repo reached a
    decision, with that decision's TTL (30 d by default, 7 d when the repo fetch failed), so
    resolved entries do not eat the next tick's searches. At most
    `RESOLVER_CALLS_PER_TICK` searches per tick, inside the tick budget AND admit's call share.
    Nothing is ever recorded with an empty id or repo: such an entry is dropped before the
    ledger with a counted `unkeyed` skip.
  - **The backlog queue (2026-11-14).** Admit never walks the launcher list alphabetically. Each tick
    `stage_admit.launcher_queue` builds the backlog with **zero calls**:
    - Entries are grouped by repo; an entry with no repo is grouped by its `launcher-<fid>` key.
    - Each group is represented by its most-downloaded entry and ranked by the group's **total
      downloads** (launcherhub's `download`, the popularity signal that costs no call).
    - Everything already decided is set aside, using local data only: memory (blocked, seen, merged),
      catalogued with a live ledger id (`scorer.catalogued_reason`), an unkeyed entry — and a repo
      whose path record carries a GitHub id that another live record decides (`_decided_by_id`): a
      repo renamed upstream and rejected under its new path (`ji1ore/remotekeyer_wifi` ->
      `Wifi_Rig_CW`, 2026-11-17) is decided by its id, in the queue and in the loop, before any fetch.
      The derived `by_repo_id` view ranks two records sharing an id by `memory._view_rank`: protected
      first, then the later-expiring one, so an expired alias never shadows the live decision.
    - Work that needs a call but decides nothing new goes to the **tail**, behind all new work: a
      catalogued repo whose id no live record holds (the rename-proof identity refresh), a live
      owner-review decision, an id an open or vetoed tick PR holds.

    Admit's call share is spent on the undecided backlog, one paid fetch per repo per tick, in an
    **interleaved order**. Even slots follow the download order; odd slots are the same repos
    shuffled with a seed of the tick's UTC hour (`_interleave`). So:
    - the top k by downloads are always within the first 2k slots;
    - an hour replays the same order, so it is reproducible;
    - the next hour explores other repos. A decision that fails to stick can never take every paid
      slot (owner, 2026-11-14: "add some random/shuffle, otherwise always fetching the same"). Every paid call ends in a remembered decision. A decision the ledger refuses
    under its own id (memory._write keeps a `merged` record, as with a renamed upstream scoring
    `duplicate_of`) is kept under the repo's note key `repo-note:<owner/repo>`, which carries no
    repo_id. So the backlog shrinks on every tick while it is not empty.

    The stage summary starts with `backlog N undecided (top: <repo>, <downloads> downloads)`.
    **Stall alarm** (`jr/admit_progress.py`, runner-local state): when the backlog does not shrink for
    `STALL_AFTER` = 3 consecutive ticks, the tick sends one Telegram nudge, and then at most one per
    UTC day. A shrinking or empty backlog clears it. An unreadable state file is a nudge, never
    silence, and a dry run counts nothing.
  - **Admission names boards with the catalog's own vocabulary (2026-11-17).** The scorer's board
    evidence is, in order: `jr/device_map.py` (the precise M5Stack sibling rules), the launcher
    category, a submission's resolved hint, then `jr/board_names.boards_named_in` over the repo's own
    words — name, description, GitHub topics (author-declared, on the repo page) and README title, not
    the README body (a support matrix names many boards; widening is Track B's job). The vocabulary is
    data/boards itself: every board's id, brand + name, aka, and its bare name only when it carries a
    digit ("T-Display-S3", "StickC-Plus2"); whole-word matches, separators optional anywhere in a term
    that carries the brand, but only at the catalog's own word breaks in a brandless one ("E-Paper S3"
    never names the PaperS3, "a tiny S3" never the TinyS3: the #1797 review), and a name that starts
    with a chip only as the catalog spells it, hyphens included ("ESP32-Ethernet-Kit", never "any ESP32
    Ethernet kit"); URLs, library and SDK references are not prose; the specific board beats the
    general one it contains. **What follows a name decides (2026-11-20, the third #1797 review).**
    Vendors sell siblings named as a catalogued name plus a word ("T-Beam Supreme", an ESP32-S3;
    "T-Embed CC1101"; "T-Display S3 Long"), and that word is an open set, so no list of suffixes is
    ever complete. A name therefore counts only when followed by the end of its text, punctuation, or a
    word of the closed list `board_names.FOLLOW_OK` (function words, "board", "firmware", "support");
    any other word makes it an unknown sibling and names nothing. Each text is read on its own (the end
    of a description is never read as followed by a topic), and a GitHub topic names a board only when
    the whole topic is one of the board's terms ("m5stickc", "lilygo-tdisplay-s3"; "t-beam-supreme" is
    not the T-Beam). The rule fails closed: a missed board is a smaller catalog, a wrong board a false
    claim; the build-file path below is the one that recovers the misses. Exactly one board is
    evidence; several is `ambiguous_board`, a skip, never a guess; none is `no_board_evidence`. The SOC
    cross-check, the device-build evidence gate and the evidence checker still run after it. Why:
    `device_map` covered 14 of 118 boards, all M5Stack; 92 of the 130 topic rejects on main were
    `no_board_evidence`, 14 of them naming a catalogued Heltec, LilyGO or StickC board in their own
    description or topics under this rule (`jr/fixtures/board_names/no_board_evidence_2026-11-17.json`;
    the first version counted 16: one was two texts glued together, one is a known miss, both noted in
    the fixture).
  - **A build-file board for every candidate (2026-11-17), not only submissions.** When the prose names
    no catalogued board (`no_board_evidence`), admit and the topics path run the device-build evidence
    gate first and take the board from the targets it already read: `device_evidence.check` returns
    `targets` ([{kind, token, url}]: every platformio `[env:*] board =`, a sketch.yaml fqbn's board, an
    ESP-IDF target chip, in file order), and `device_evidence.board_from_targets` picks the first token
    `board_alias.resolve_token` maps to a catalogued board. A chip-only target (`esp32s3`, `esp32dev`) is
    a chip, not a board: no devkit is ever guessed, the candidate stays `no_board_evidence`. The board
    enters the scorer as the hint (the submission path's own mechanism), so the first recipe cites the
    build file and line, and the gate is not run twice. Why: 8 of the 76 above-floor `no_board_evidence`
    rejects of 2026-11-17 carried a root platformio.ini whose `board =` was a catalogued board
    (esp32-s3-devkitc-1, esp32-c3-devkitm-1, lolin-s3-mini, lilygo-t-display-s3, m5stick-c), e.g.
    esp32-c3-adblock (3,597 stars) and project_aura (797).
  - **The GitHub-topics source remembers every paid decision (2026-11-16).** `jr/stage_admit_topics.py`
    scores at most `budget * SCORE_MULTIPLIER` prefiltered repos per tick, in the search's star order
    (`SCORE_MULTIPLIER` 10 since 2026-11-18, from 5: measured ticks spent a third of their call budget).
    Every repo it paid a metadata fetch for ends in a remembered decision, the launcher's rule: a
    scorer skip (`no_board_evidence`, `library_*`, `archived`, `duplicate_of`, ...), an unreadable
    repo (`repo_unresolved`) or an id the ledger already holds (`already_*`) is recorded `rejected`
    under the repo's note key `repo-note:<owner/repo>` with `stage_admit.REJECT_TTLS` (archived 90 d,
    unresolved 7 d, anything else 30 d). Below-floor and device-evidence skips keep their own records,
    and a repo an open tick PR holds is never recorded. So the next tick's prefilter walks past them to
    the next repos of the same search. Before this rule the skips were forgotten: for 24 ticks
    (Nov 15-16) every topic pair re-scored the same top 10 with `scored_clean=0`, while 6 of the 24
    pairs held 428 prefiltered repos behind them (read-only search, 2026-11-16).

    Why: from 2026-11-12 to 2026-11-14 the alphabetical rescan re-paid for catalogued repos every tick
    and stopped before brucedevices/firmware every hour (Bruce has ~35 entries under "B"). 1,205
    undecided repos with 1.35 M downloads were never reached, and nothing said so.

    **Decisions held in open tick PRs are carried (2026-11-14).** A tick starts from `origin/main`, and
    its decisions live in its own PR. A `jr-review` PR waits for the owner, and a superseded
    bookkeeping PR is closed, so their decisions never reached main and the next ticks paid for them
    again (15Z→16Z on 2026-11-14: backlog 1200→1199, 17 of 41 decisions re-paid). Now every tick:
    - in the preflight, **before any superseded PR is closed**, reads the ledger each eligible open
      tick PR committed (`pending_prs.eligible`, one raw read at its pinned `headRefOid`, only when the
      PR changes that ledger; unreadable = a warning, never an abort);
    - in the memory step, after the open-PR hydration, applies `memory.carry_decisions`: a live
      `seen`/`rejected` record **with `expires`** and no `review` block is copied when this ledger
      lacks it or holds an older unprotected one that is not a live owner-review decision. What the
      older record knew is kept as `memory._write` keeps it: its history and itself go into `history`,
      aliases are unioned (#1705 review, 2026-11-14). Never over a merged, proposed or permanent
      record, never under a repo id another protected record owns: `memory._write`'s refusals, so
      `scripts/ledger_guard.py` passes by construction. Proposals stay `hydrate_open_pr_ledger`'s and
      owner-review decisions `review_memory`'s.

    The carried decisions ride this tick's PR (a carry alone publishes a memory-reconciliation PR), and
    the PR body says `Carried N decision(s) from open tick PR(s) #…`. So the backlog guarantee above
    holds even while a review question waits.
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
  firmware against newly-added boards. **HOW to read "what the repo supports" (ranked build
  signals: release `.bin` names → `platformio.ini` → CI matrix → `boards.txt` → README), the
  per-board provenance to store, and the two guard checks that make this a hard gate
  (completeness + destructive-prune guard) live in `SPEC-firmware-boards.md` — that spec is the
  method, this job is its executor.**
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

**Wiring (RESOLVED + PROVEN LIVE 2026-08-27 — no service-account key):** GA4 property
`properties/551132215` + Search Console `sc-domain:esp-atlas.com`, pulled through the **Composio
SDK** (`~/.composio-venv`, API key at `~/.composio.key`, entity `7UQIn73xcX…`) using the
`google_analytics` + `google_search_console` toolkits (OAuth-connected for Jr's entity — the auth
was the missing piece; connected via `connected_accounts.initiate` links). Actions:
`GOOGLE_ANALYTICS_RUN_REPORT`, `GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY` / `LIST_SITES`.
First live pull: 79 users / 245 impressions / pos 32.2. **`jr/telemetry.py`, weekly cron
`jr-telemetry` (Mon 09:07).** The SA-key route is abandoned — Composio OAuth is simpler and
proven. *(Lesson: a Composio toolkit being connected in the dashboard ≠ connected for the
agent's entity — initiate the connection per-entity and send the OAuth link.)*

**Weekly digest (Jr → Telegram/webhook), consolidated GA4 + GSC:**
- **Users / traffic**: active users, new users, sessions, week-over-week Δ, and **progress toward 1MM**.
- **Acquisition**: top channels, top landing pages, top countries.
- **Search (GSC)**: total clicks/impressions/CTR/avg-position Δ; **top queries**; **rising queries**;
  **high-impression / low-CTR pages** (title/desc opportunities); indexed-coverage changes.
- **Health**: Core Web Vitals / PSI trend; 404s (feeds the liveness/NotFound signal).

**Raw vs spam-adjusted GA4 (2026-11-10):** the GA4 line prints the **raw** no-dimension distinct
total (active users / sessions, unchanged) beside **spam-adjusted** sessions and engaged sessions.
Adjusted = raw minus the `sessionSource` rows (a second GA4 report: sessions, engagedSessions,
averageSessionDuration) whose host is in the committed `jr/referral_denylist.json` (each entry:
`host`, `reason`, ISO `added_on`; a malformed file raises — the digest fails closed rather than
publish unfiltered numbers) and minus the rows matching the behavioural junk rule
(`_is_junk_segment`; source `(direct)` is the Direct channel). A row matching both is excluded
once. Two **28-day growth deltas** follow, one line each with ↑/↓/→ and both numbers: GSC clicks
and adjusted engaged sessions for the completed 28-day window vs the 28 days before it.

**Bot rules aligned with deep-analytics (owner-approved 2026-11-20):** the adjustment breakdown is
`sessionSource × city × sessionDefaultChannelGroup × screenResolution × browser` with an explicit
row `limit`. Every session lives in exactly one row and every rule's group key is a function of the
row key, so a session matched by several rules is excluded once. Each rule judges the aggregate of
its own group, then claims every row in a matched group; a row is attributed to the first matching
rule, in this order: (1) **fast unengaged** — a source × city × channel segment outside the
human-arrival channels (`HUMAN_CHANNELS`, unchanged since 2026-11-18) with avg duration ≤ 5s and
engagement ≤ 10%; (2) **referral denylist** — any channel; (3) **zero-engaged source** — a
`sessionSource` with ≥ 5 sessions and 0 engaged; (4) **screen 800x600** with engagement ≤ 10%;
(5) **browser Android Webview** with engagement ≤ 10%. Rules (3)–(5) apply to every channel except
Organic Search, whose rows neither count toward nor get removed by them. Thresholds are module
constants in `jr/telemetry.py`. A response at the row limit, or whose `rowCount` exceeds the rows
returned, is treated like a failed fetch (spam-adjusted and the 28d adjusted delta print
`unavailable`). Both 28d windows use the same rules. A `🧹` line under the GA4 line names how
many sessions each rule removed.

**The steering loop (this is why it's Jr's, not a bystander's):** GSC **demand** is a first-class
**data-priority signal** — queries with impressions but no matching record, or a thin one, jump
the staleness/population queue. *People are searching for a board/firmware we don't cover well →
Jr prioritizes authoring/deepening it.* Analytics thus steers **which data Jr keeps**, closing the
loop between what users want and what the atlas provides — without Jr ever touching growth levers.

**The steering rule, rewritten from measurement (owner, 2026-11-17).** Between 2026-11-03 and 11-17 every
demand snapshot held 0 `UNCOVERED` items, so the one wire from demand to the hourly split (a bias of at most
one unit in six, `jr/allocator.py`) was 0.0 for two weeks, and 50 consecutive ticks (Nov 15 19Z → Nov 17
20Z) produced nothing: admitted 0, backfilled 0, recipes 0, topics authored 0, while coverage sat at
61.7 % and the four largest gauge gaps (pinout, download_mode, usb_serial, dimensions_mm) had no stage able
to write them. The rule therefore becomes:

1. **Three lanes, split by yield.** New boards (the demand executor, one a day), deepening existing boards
   (the hourly backfill through deterministic resolvers) and new firmware (admit, boardmap, topics). A yield
   ledger (`docs/telemetry/yield.jsonl`, one row per stage per tick) feeds the allocator; a lane with zero
   yield over the window drops to its floor and its units go to the lane that produces; constants live in
   a committed `jr/steering.json` and every tick prints the inputs of its split.
2. **Demand orders, the gauge fills.** `UNCOVERED` still jumps the queue. `RANKS_POORLY` and page
   impressions ORDER which vendor × field gets a resolver first; they never change SEO text (owner's).
3. **The model boundary: an LLM solves code problems, never fills inventory.** The delegate's work items are
   resolvers (vendor × field, fixture page + RED test), stage fixes and CI fixes; the only record it authors
   is a brand-new board under the executor prompt. Catalog values come from deterministic resolvers so each
   is reproducible from its cited page.
4. **A stalled lane dispatches the coding agent.** Zero yield over the stall window (`jr/steering.json`),
   `scored_clean == 0` over the topics window, or an identical demand snapshot seven days running is an
   incident of kind `stall` in `jr/ci_watch.py`, claimed by the same heal launcher, same caps and `ack`,
   same `jr-heal` review route; the prompt diagnoses from the yield rows first and fixes or reports.
5. **Humans hold kill switches and audit after the fact**: `jr/autonomy.json` (`demand_automerge`,
   `tick_automerge`, `code_automerge`, `stall_dispatch`; each turned on by a reviewed PR) + the matching
   repository/runner variables as instant kills (`JR_*=0`); every tick PR body ends with an **Autonomy
   audit** block (the split and the lanes' yield over the window, stall incidents recorded/resolved, demand
   work by class and state from main's receipts, `jr/report.render_audit_section`); the weekly digest.

**RESOLVED ⟨Q14⟩ — Jr hosts the telemetry cron + digest** (its crons + §7 outbound + the
data-priority tie-in make it the natural home), under the hard boundary above: measure / report /
steer-data only — never a growth lever.

**RESOLVED ⟨Q15⟩ — both outputs**: a **weekly Telegram summary** AND a committed
`docs/telemetry/<date>.md` snapshot (git-tracked history, so trends are auditable).
**1MM is a horizon with no date** (owner, 2026-11-10; it replaced the 2026-11-27 target date set on
2026-08-27) — the digest prints the goal line and the two 28-day deltas above; the operational goal is
every completed 28-day window ≥ the previous one (`BIBLE-PLAN.md`, "Growth goal").

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
On acceptance: fold the good of `SPEC-freshness / -data-population / -discovery` into this
file (`SPEC-data-maintainer.md` already deleted 2026-08-30, superseded here), update
`SPEC-INDEX.md` ownership, and leave a one-line tombstone in each old spec pointing here.

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

*Resolved: Q1 (own instance on the Pi) · Q1b (harness = Agno, tested) · Q2/Q3 (hybrid
cadence + liveness-privileged) · Q4 (auto-author cheap, Issue for judgment) · Q5 (keep
`example`, defer `prompt-recipe`) · Q6 (trust-promotion mechanism) · Q7 (3 inbound hooks,
Felipe-only) · Q8 (Groq free `gpt-oss-120b` primary; Laguna deferred, throttled) · Q8b (≤10 PRs/day)
· Q9 (B/C-series deferred) · Q10 (defer companion) · Q11 (Reddit title+selftext+top-10, score>50)
· Q12 (all 8 makers) · Q13 (PlatformIO + ESP Component registries) · **Q1b (harness = Agno)**.*
