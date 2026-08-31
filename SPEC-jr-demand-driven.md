# SPEC — EspAtlas Jr, Demand-Driven 🎯 (search what's actually searched)

> Status: **DRAFT — for review (2026-08-31).** Not converged. `⟨Q⟩` markers are open
> questions for Felipe. This spec **extends** `SPEC-espatlas-jr.md` — specifically it
> builds out **§3d Growth telemetry** from a printed digest line into Jr's actual work
> driver. It **depends on** the deterministic scorer (`jr/scorer.py`, promoted from
> `jr/spike/` on 2026-08-31) for entity resolution. Nothing here unpauses `jr-daily`.
>
> **Motto inherited unchanged** (`SPEC-espatlas-jr.md §2`): bot proposes, humans dispose;
> deterministic guard gates every PR; auto = `unverified`. Demand only changes *what Jr
> works on first* — never *whether the guard/human still decide*.

---

## 0. The reframe (why this is not trivial)

Today Jr drains the launcher backlog by **staleness** (oldest-uncatalogued entry wins).
That is supply-side and blind: it authors firmware in catalog order regardless of whether
a single human has ever looked for it. For a north-star of **1,000,000 users by
2026-11-27**, that is the wrong queue. The right queue is **demand**: the firmware, boards,
and parts people are *already typing into Google and into esp-atlas.com's own search box
and not finding a good answer for*.

The reframe in one line:

> **Jr should author, first and loudest, the things people are already searching for and
> failing to find on esp-atlas.com — measured, not guessed.**

Why it's genuinely hard (the four non-trivial problems this spec must solve):

1. **Signal → entity.** A demand signal is free text (`"marauder cardputer"`,
   `"flipper esp32 evil portal"`). Turning it into *which catalog entity is missing* is a
   fuzzy-match/entity-resolution problem. **Solved by reusing the scorer's deterministic
   maps** (§4) — not a new LLM guess.
2. **Demand ≠ authorize.** "Searched a lot" must not become "author anything." A junk
   fork with 3000 impressions is still junk. The scorer + guard stay the arbiter (§7).
3. **Attribution / proof.** Did authoring a demanded firmware *actually* convert demand
   into users? Without a feedback measurement the loop is faith, not engineering (§10).
4. **Cold-start + privacy.** GSC hides rare queries (k-anonymity); a thin new site has
   sparse query data; site-search may not be tracked. The spec must degrade honestly (§8).

---

## 1. The demand→supply loop (the architecture)

```
   ┌─────────────────────── DEMAND (what people want) ───────────────────────┐
   │  GSC query-gap   ·   GA4 site-search zero-results   ·   GA4 404 hits     │
   └───────────────────────────────┬─────────────────────────────────────────┘
                                    │  jr/demand.py  (miner)
                                    ▼
                       ranked List[DemandItem]  (term, volume, gap-type)
                                    │
                                    │  jr/scorer.py maps  ── device_map / capability_map
                                    ▼
                    entity resolution + gap classification (§4)
              UNCOVERED  ·  RANKS_POORLY  ·  COVERED_OK(skip)
                                    │
                                    │  demand queue (§5) — priority, not staleness
                                    ▼
   ┌─────────────────────── SUPPLY (find & author) ──────────────────────────┐
   │  launcherhub · GitHub · m5burner  →  scorer authors record  →  guard PR  │
   └───────────────────────────────┬─────────────────────────────────────────┘
                                    │  human merges (unchanged contract)
                                    ▼
                    published page for the demanded thing
                                    │
                                    │  next GSC cycle measures uplift (§10)
                                    ▼
                       feedback: did impressions → clicks?   ── loop closes
```

The loop is **closed**: the same GSC that surfaced the gap measures, two cycles later,
whether filling it converted. That measurement is what makes this an engineering system
and not a vibe.

---

## 2. Demand sources (what's real, what needs verifying)

| # | Source | Composio tool | What it means | Status |
|---|---|---|---|---|
| D1 | **GSC query-gap** | `GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS_QUERY` (dims `[query]`, and `[query,page]`) | Terms where esp-atlas **already appears** (impressions) but wins little — high-impression + low-CTR + weak-position = *we rank but have no good page*. **The gold.** | **[REAL]** — `jr/telemetry.py` ships these weekly today |
| D2 | **GA4 on-site search** | `GOOGLE_ANALYTICS_RUN_REPORT` (dim `searchTerm`, metric `eventCount`; zero-result via a `no_results` param/event) | Terms typed into esp-atlas.com's **own search box** — the purest intent. Zero-result terms = direct catalog gap. | **[PARTIAL] — ⟨Q1 RESOLVED 2026-08-31⟩:** events fire (**1,424 in 90d**) but `searchTerm` is **empty** → term-capture not configured. Plumbing exists; one **site-code fix (ours, not Jr)** unlocks it. |
| D3 | **GA4 404 / not-found** | `GOOGLE_ANALYTICS_RUN_REPORT` (dim `pagePath` filtered to the 404 route/title) | URLs people reached that don't exist — often a firmware/board slug they expected us to have. | **[UNVERIFIED]** — depends on 404 page fires a GA4 event ⟨Q2⟩ |
| D4 | **GSC query+page** | same as D1, dims `[query, page]` | Which existing page a query lands on → find queries with **no** owning page (gap) vs pages that under-convert (improve). | **[REAL]** — same tool, extra dimension |

**Reliability caveats baked into the spec:**
- **GSC k-anonymity:** rare queries are omitted by Google entirely. A brand-new niche
  firmware with <~10 searches/period is **invisible** — D2/D3 (first-party) catch what GSC
  cannot, which is why site-search is worth enabling (⟨Q1⟩).
- **GSC lag:** data is ~2–3 days behind; freshest signal is stale by design → weekly mine
  cadence, not daily (§11).
- **Position/CTR noise:** low volume rows are statistically thin. The miner applies a
  **minimum-impressions floor** before a term is eligible (§3).

---

## 3. The demand miner — `jr/demand.py` (new)

**Purpose:** pull D1–D4, normalize, floor-filter, dedup, and emit a ranked
`List[DemandItem]` — **zero LLM**.

**Inputs:** the Composio calls above (reuse `telemetry.py`'s `_ex()` executor and
credentials verbatim — same `ENTITY`, `GA4_PROPERTY`, `GSC_SITE`; do not fork the auth).

**Algorithm (deterministic):**
1. Pull D1 `[query]` and D4 `[query,page]` for the window (default 28d — wider than the
   digest's 7d, to beat k-anonymity and smooth noise).
2. Pull D2/D3 if available (⟨Q1/Q2⟩); tag each term with its `source`.
3. **Floor-filter:** drop rows below `MIN_IMPRESSIONS` (D1/D4) or `MIN_EVENTS` (D2/D3) —
   thresholds versioned constants, tuned on real data, not hard-guessed.
4. **Normalize** each term: lowercase, strip, collapse whitespace, canonical device
   aliases (`stickc plus2` → `m5stickc-plus2`) via the scorer's `device_map` alias table.
5. **Dedup/merge** near-duplicate terms (same resolved entity → one item, volumes summed).
6. **Score demand weight** per item — a transparent formula, e.g.
   `weight = impressions × (1 − ctr) × position_penalty(position)` for D1 (high impressions
   we're *not* capturing rank the most), plus first-party terms (D2/D3) weighted higher
   (purest intent). Formula is a versioned, tested function — improvable like the scorer.

**Output:** `List[DemandItem]` (schema §9), ranked by `weight` desc. Git-tracked snapshot
per run under `docs/demand/<date>.json` (auditable, diffable, like telemetry snapshots).

---

## 4. Entity resolution — the bridge to the scorer (the crux)

A `DemandItem.term` is free text. To become work it must resolve to **which catalog entity
is missing/weak**. This **reuses `jr/scorer.py`** — no new intelligence:

1. **Term → entity candidates.** Run the term through the scorer's `device_map`
   (device/board tokens) and `capability_map` (category/capability tokens) as a *parser*:
   extract any board (`cardputer`, `stickc-plus2`), chip (`esp32-s3`), or firmware/capability
   token (`marauder`, `evil-portal`, `deauth`) present in the term.
2. **Gap classification** — join resolved entity against the current atlas (`index.json` /
   `esp-atlas.db`):
   - **`UNCOVERED`** — resolved entity (or firmware×board pair) has **no** catalog record
     → this is a *populate* job → hand to supply search (§6).
   - **`RANKS_POORLY`** — record exists but D1 shows high-impression/low-CTR/weak-position.
     **RESOLVED ⟨Q3⟩ (2026-08-31): Jr does NOT code.** A content/SEO gap routes to
     **Felipe + DasBrowCoder** as a human/agent task (a report to us), **never** Jr's
     authoring path. Jr's lane is strictly authoring catalog records for `UNCOVERED`.
   - **`COVERED_OK`** — record exists and converts fine → **skip** (already served).
   - **`UNRESOLVED`** — term maps to no known entity (e.g. `"esp32 tutorial pdf"`) →
     bucket to a `unresolved_demand.json` review list; **never** author from an unresolved
     term. High-volume unresolved clusters are a signal *to Felipe*, not to the authoring
     path (could mean a whole missing category).

This is why the scorer had to exist first: **demand resolution and supply authoring share
the exact same deterministic maps**, so a term and a catalog entry are judged by one
consistent brain. Divergence here would reintroduce the whack-a-mole the rethink killed.

---

## 5. The demand queue (replaces staleness as Jr's prioritizer)

`SPEC-espatlas-jr.md §3` runs expensive jobs off a **staleness queue** (oldest-`verified`
wins). This spec **inserts a demand queue in front of it** for the *populate/discover*
verbs, while leaving **liveness privileged** (the motto) untouched:

**Per daily tick, budget-bounded (`$5/mo` cap unchanged), order:**
1. **Liveness sweep** — always first (`§3 RESOLVED ⟨Q3⟩`, unchanged). Non-negotiable.
2. **Demand queue** — top-`weight` `UNCOVERED` items from the latest demand snapshot that
   aren't already in `proposed.json` (dedup ledger, reused) → supply search + author (§6).
3. **Staleness queue** — remaining budget drains oldest uncatalogued launcher entries
   (the current behavior, demoted to *backfill* — it keeps breadth growing when demand is
   exhausted for the tick).

So demand **steers**, staleness **backfills**, liveness **guards**. No job is deleted; the
priority order changes. ⟨Q4⟩: exact split — e.g. 70% budget to demand, 30% to staleness
backfill, or fully demand-first-then-spill?

---

## 6. Closing the loop — supply search for an UNCOVERED demand

Given an `UNCOVERED` `DemandItem` resolved to entity `E` (e.g. firmware `marauder` × board
`cardputer`), Jr must *find an authorable source*, in priority order:
1. **launcherhub `giveMeTheList`** — is there a catalog entry matching `E` not yet drained?
   (most likely; the term often *is* in the launcher list). Run the **scorer** on it →
   authored record or skip-reason.
2. **GitHub** — search the firmware repo for a release/`.bin` targeting board `E`; scorer's
   fork-check rejects forks of already-catalogued repos (the #74 failure mode).
3. **m5burner** (M5 devices) — vendor firmware index.

If a clean source is found → scorer authors → **deterministic guard → cited PR** (unchanged
pipeline). If none is found → emit an **Issue** ("high demand for `E`, no clean upstream
firmware located") — that is itself valuable intelligence for Felipe. **Jr never fabricates
a record to satisfy demand** (§7).

---

## 7. Guardrails (demand must not lower the bar)

1. **Scorer + guard still gate every PR** — a demanded firmware that fails schema /
   sources-live / fork-check / soc cross-check is **blocked**, exactly as today. Demand
   changes order, never admissibility.
2. **No author-from-unresolved** (§4 `UNRESOLVED`) — free-text demand with no entity match
   never reaches the authoring path.
3. **Fork/dup demand trap** — a term matching an already-catalogued repo's fork resolves to
   `COVERED_OK` (skip), not a second record.
4. **Demand poisoning** — GSC/site-search are open surfaces; a burst of adversarial
   searches could try to steer Jr. Mitigations: floor-filter, entity-resolution requirement
   (nonsense terms → `UNRESOLVED`, never authored), human-merge backstop (worst case = a
   rejected PR). Documented threat, bounded blast radius.
5. **Privacy** — GSC is already k-anonymized upstream; site-search terms are stored only as
   aggregated snapshots (`docs/demand/`), never raw per-user. No PII enters the repo.

---

## 8. Cold-start & degradation (honest failure)

- **Thin GSC data** (new/small site): D1 sparse. Bootstrap with **category-level demand** —
  broad terms (`"esp32 marauder"`, `"m5 firmware"`) resolve to *categories* not exact SKUs;
  fill category breadth so pages exist to *earn* impressions, then D1 sharpens next cycle.
- **Site-search off** (⟨Q1⟩): D2/D3 unavailable → miner runs on D1/D4 only and **says so
  loudly** in the digest ("first-party demand blind — enable GA4 site-search"). No silent
  degradation.
- **All demand exhausted for a tick:** queue falls through to staleness backfill (§5.3) — Jr
  is never idle, never blocked on demand.

---

## 9. Data model

```jsonc
// DemandItem — one resolved unit of demand
{
  "term": "marauder cardputer",           // normalized query
  "raw_terms": ["marauder cardputer", "cardputer marauder"], // merged sources
  "source": ["gsc_query", "ga4_sitesearch"],
  "impressions": 1840, "clicks": 22, "ctr": 0.012, "position": 18.4, // D1 (nullable)
  "events": 37, "zero_result": true,      // D2/D3 (nullable)
  "weight": 1795.2,                        // §3 formula output
  "resolved": {                            // §4 scorer output (nullable)
    "board": "m5-cardputer", "chip": "esp32-s3",
    "firmware_token": "esp32marauder", "capability": ["wifi-attack","deauth"]
  },
  "gap": "UNCOVERED",                       // UNCOVERED|RANKS_POORLY|COVERED_OK|UNRESOLVED
  "landing_page": null,                     // D4 (nullable)
  "first_seen": "2026-08-31", "last_seen": "2026-09-27"
}
```

- **Snapshots:** `docs/demand/<date>.json` (full ranked list, git-tracked, diffable).
- **Ledger reuse:** authored demand items flow through the existing `proposed.json` dedup
  ledger — no parallel state.
- **Unresolved review list:** `docs/demand/unresolved.json` (high-volume `UNRESOLVED`
  clusters for Felipe — potential missing categories).

---

## 10. Feedback measurement — proving the loop works (§0.3)

The loop is only real if we can show authoring a demanded thing **converted** it. For each
demand item Jr authored, record `authored_date` + the target page slug. Then on each later
mine, compute per-page **uplift**: impressions and clicks on that slug **before vs after**
authoring (D4 `[query,page]`). Emit in the weekly digest:

> *Demand→supply scoreboard: 12 gaps filled last 4 wks → +3,400 impressions, +180 clicks on
> those pages (avg position 22 → 9).*

That scoreboard is the single most important number for the 1MM goal — it says whether the
engine actually turns searches into users, or just authors pages nobody clicks. ⟨Q5⟩: is a
naive before/after acceptable v1, or do we need a hold-out (some gaps deliberately unfilled)
to control for site-wide trend?

---

## 11. Cadence & crons

| Job | Cadence | Why |
|---|---|---|
| **Demand mine** (`jr/demand.py`) | **weekly** (fold into existing `jr-telemetry` Mon 09:07) | GSC ~2–3d lag; weekly smooths noise, beats k-anonymity |
| **Demand queue drain** | **daily** (inside `jr-daily`, once unpaused) | consumes the weekly snapshot top-down, budget-bounded |
| **Feedback scoreboard** | weekly (in the digest) | measures uplift |

No new cron process — demand mining **extends `jr-telemetry`** (already active, harmless);
demand *draining* rides the (still-paused) `jr-daily` tick when it returns.

---

## 12. Rollout (phased, TDD, jr-daily stays paused)

- **Phase 1 — Miner + resolution, read-only.** `jr/demand.py` pulls D1/D4 (+D2/D3 if
  enabled), floor-filters, resolves via scorer, classifies gap, writes `docs/demand/`.
  **Golden test:** a fixture of real GSC rows → expected `DemandItem`s + gap labels. No
  authoring. Ship the ranked demand snapshot to Telegram for Felipe to eyeball vs reality.
- **Phase 2 — Demand queue, dry-run.** Wire the queue ahead of staleness (§5) but in
  **dry-run**: log what Jr *would* author from demand, don't open PRs. Verify the top-N are
  things Felipe agrees are worth having.
- **Phase 3 — Live, gated.** Demand items author real PRs through the unchanged guard. Only
  now consider unpausing `jr-daily`, and only after a demand batch runs clean end-to-end on
  the golden set.
- **Phase 4 — Feedback scoreboard.** Add uplift measurement (§10) once ≥2 GSC cycles of
  filled gaps exist to measure.

Each phase = its own delegated task, TDD, guard-gated, on a branch. `jr-daily` unpauses
**only at Phase 3**, and only on Felipe's explicit call.

---

## 13. Open questions ⟨Q⟩ — need Felipe

- **⟨Q1⟩ RESOLVED (2026-08-31):** Site-search events **do** fire — **1,424 in 90d** — but the
  `searchTerm` value is **empty** (term-capture not configured). D2's plumbing exists; one
  site-code fix (populate `search_term` / GA4 query-param) unlocks 1,424 searches of pure
  intent. **That fix is ours (site code), not Jr.** Phase 1 proceeds on GSC (D1/D4, confirmed
  live) in the meantime; D2 lights up once term-capture is fixed. → **new task for us.**
- **⟨Q2⟩** Does the 404 page **fire a GA4 event** we can query (D3)? If not, cheap to add.
- **⟨Q3⟩ RESOLVED (2026-08-31): Jr does not code.** `RANKS_POORLY` (content/SEO) is **ours
  (Felipe + DasBrowCoder)**, never Jr. Jr's lane is authoring catalog records for `UNCOVERED`.
- **⟨Q4⟩** Demand-vs-staleness budget split (§5) — demand-first-then-spill, or a fixed %?
- **⟨Q5⟩** Feedback measurement (§10) — naive before/after v1, or hold-out for rigor?
- **⟨Q6⟩** Demand window — 28d default OK, or match the digest's 7d for freshness?

---

## 14. Non-goals

- **Not** an SEO/content-marketing engine — Jr authors *catalog records*, not blog posts.
  `RANKS_POORLY` may hand off elsewhere (⟨Q3⟩).
- **Not** an LLM reintroduction — the whole loop is deterministic (miner formula + scorer
  maps). No model in the demand→entity→author path.
- **Not** a bypass of the contract — bot proposes, human disposes, guard gates. Demand only
  reorders the queue.
- **Not** live until Phase 3, and `jr-daily` stays paused until then.
