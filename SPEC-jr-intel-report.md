# SPEC — Jr Intelligence Report 🛰️ (360° site watch, warns Felipe)

> Status: **DRAFT — for review (2026-08-31).** Extends `SPEC-espatlas-jr.md §3` (the job
> map) into a **unified daily/weekly report**. Depends on the built demand miner
> (`jr/demand.py`) and telemetry auth (`jr/telemetry.py`). `⟨Q⟩` = open for Felipe.
>
> **Read-only.** This is a *reporting/warning* system, not an authoring one. It **never
> writes the atlas** and does **not** require unpausing `jr-daily` (which stays paused —
> that's the authoring lane). The report only *watches* and *warns*; Felipe (or a later,
> separately-gated authoring step) acts.

---

## 0. What it is

Jr is not a demand-miner — it's a **360° site-intelligence agent**. It watches everything
about esp-atlas across the seven signal sources below, and delivers **one report** on two
cadences, ending with the only thing that needs a human: **⚠️ WARNINGS**.

The design realizes the `SPEC-espatlas-jr.md §3` job map — already fully specced, mostly
unbuilt — as a single consolidated read, instead of scattered jobs that fire into the void.

---

## 1. Two cadences + warnings

- **Afternoon pulse (light, recurring)** — **RESOLVED ⟨Q2⟩ (2026-08-31):** runs *repeatedly
  through the afternoon* and **only messages Felipe when there's a 🟡/🔴 warning** — no "all
  green" pings, ever. Cheap watches only, LLM-free. Silent by default; it speaks solely to warn.
- **Weekly (deep read)** — the full picture: demand map, every discussion/bug thread triaged,
  health scorecard, drift report, manufacturer news. Folds into the existing `jr-telemetry`
  Monday digest.
- **Every report ends with `⚠️ WARNINGS`** — *only* the items that need Felipe (§4). If the
  section is empty, the report says so plainly ("nothing needs you") so silence is trustworthy.

The daily pulse is **suppressible** (`[SILENT]`) when nothing new and nothing to warn —
same convention the cron layer already uses — so it's a signal, not noise.

---

## 2. Signal sources (the 360)

| # | Signal | Source · fetch | Warn trigger | Status |
|---|---|---|---|---|
| S1 | **Demand** | GSC/GA4 via Composio (`jr/demand.py`) | new high-weight `UNCOVERED`; a `RANKS_POORLY` worsening | **built ✅** |
| S2 | **Upstream firmware READMEs** | each catalogued firmware repo's **README** (raw/`gh api`) | the README **adds a new device/board** we don't cover, **changes a capability**, or **drops a device** (compat) — diffed vs our catalog | **new — build first** |
| S3 | **OUR-repo bugs + discussions** | **esp-atlas's own** GitHub **Issues + Discussions** (fcavalcantirj/esp-atlas), via `gh` | a **user-reported bug / bad-data** on our pages, a feature request, a question | **new — build first** |
| S4 | **Firmware releases** | GitHub Releases per catalogued firmware | a release whose `.bin`/device list **drifts** from our recipe | new |
| S5 | **Liveness / dead sources** | HTTP-check every cited `sources[].url` | a **dead citation** (motto broken) or a redirect | new (reuse `check_sources_live` if present) |
| S6 | **Recipe/compat drift** | firmware repo `User_Setup`/`#define`/README device lists vs our recipes | a recipe that **stopped matching** upstream | new |
| S7 | **Manufacturer watch** | Espressif products/datasheets, M5 docs/M5Burner | a **new chip/board** the day a vendor posts it | new |

Build order (§6) front-loads **S2/S3** — the two are *different sources* (do not conflate):
**S2 = OTHER repos' READMEs** (what upstream firmware now supports, vs our catalog);
**S3 = OUR repo's bugs + discussions** (what users report about esp-atlas itself). This is the
signal Felipe is blind on today and explicitly asked for.

---

## 3. Architecture

**Deterministic-first, LLM-optional.** Each signal is a small module: `fetch()` (live) →
`classify()` (pure rules) → `diff_vs_ledger()` (only surface *new/changed*) → contributes
rows to the report + any warnings.

- **Fetch:** `gh` CLI / GitHub API for S2–S6 (auth already present); Composio for S1;
  plain HTTP for S5/S7. Rate-limited, official APIs only (motto §2.5).
- **Classify:** rules/keyword/label maps (e.g. an issue titled "support for Cardputer" →
  `new-device-request`; a label `bug` or body matching a device we list → `compat-risk`).
  **Reuse the scorer's device/capability maps** to resolve which of *our* records a thread
  is about — same entity-resolution brain as demand + authoring.
- **Summarize (optional):** an LLM (OpenRouter/Groq free-tier, under the **`$5/mo` cap**,
  `jr/spend.json`) may *phrase* the weekly deep digest more readably — but **out of the
  critical path**: every fact it prints must already exist in the deterministic rows
  (cite-or-omit), so it can't invent a warning. Daily pulse uses **no LLM**.
- **Deliver:** `jr/notify.py` (Telegram) + a git-tracked snapshot under `docs/intel/<date>.md`
  (diffable history, like `docs/telemetry/`).

---

## 4. WARNINGS — the only part that needs a human

A warning is raised **only** for a *new or changed* item (deduped against the ledger, §5) in
one of these classes, so the section stays small and trustworthy:

| Severity | Class | Example |
|---|---|---|
| 🔴 **Act** | dead citation (S5); user bad-data report (S3); a recipe broken by an upstream release (S4/S6) | "`sources[2]` on esp32-c6 → 404 — motto broken" |
| 🟡 **Decide** | new-device request with real demand (S2×S1); a new chip/board (S7) | "12 users asked for Cardputer + Marauder; no recipe exists" |
| 🟢 **FYI** | ranking movement (S1); routine upstream chatter | "esp32-c6 moved #30→#24" |

Routine status (counts, healthy checks) lives in the report *body*, never in WARNINGS. The
rule: **if it doesn't need Felipe, it isn't a warning.**

---

## 5. Data model & anti-spam

- **Ledger** (`docs/intel/ledger.json`, or reuse `proposed.json`'s pattern): every surfaced
  item keyed by a stable id (repo#issue, source-url, release-tag). We warn **once** per item,
  and again only if its state changes. No re-warning the same dead source every day.
- **Report snapshot** (`docs/intel/<date>.md` + a `.json` sidecar): the full structured read,
  git-tracked and diffable.
- **Per-signal record**: `{signal, id, entity (resolved via scorer maps), class, severity,
  first_seen, last_seen, url, summary}`.

---

## 6. Build order (one signal at a time, validate each — Felipe's rule)

1. **S2 + S3 — the watch** *(first, per Felipe)* — two distinct sources:
   - **S2 = OTHER repos' READMEs:** fetch each catalogued firmware repo's README, diff vs
     last-seen (ledger) and vs our catalog → new device/board support, capability change,
     dropped device. Resolve entity via scorer maps.
   - **S3 = OUR repo's bugs + discussions:** `gh`-fetch new Issues + Discussions on
     fcavalcantirj/esp-atlas, classify (bug / bad-data / feature-request / question).
   Both ledger-deduped, emit rows + warnings. TDD with fixture payloads. Read-only.
2. **S5 — liveness/dead-sources**: HTTP-check cited sources, warn on dead/redirect.
3. **S4 — release/version-drift**: GitHub Releases vs our recipe version.
4. **Consolidate — the report**: daily pulse + weekly deep, WARNINGS section, `docs/intel/`
   snapshot, Telegram delivery. Wire into a **new `jr-intel-daily` cron (light)** + fold the
   deep read into **`jr-telemetry` weekly**. `jr-daily` stays paused.
5. **S6 recipe/compat drift**, then **S7 manufacturer watch** — the deeper, expensive watches.

Each step: deterministic, TDD (80%+), guard-gated, on a branch, verified, merged. No LLM in
the critical path; optional summarizer only at step 4's weekly digest, under the cap.

---

## 7. Guardrails

- **Read-only** — no atlas writes, no PRs from this system; it *reports*. (Authoring stays the
  separate, still-paused `jr-daily` lane.)
- **No spam** — ledger-dedup means each item warns once; empty WARNINGS says "nothing needs you."
- **Motto-safe** — the optional LLM summarizer can only rephrase deterministic rows; it cannot
  originate a fact or a warning.
- **Cost** — `$5/mo` cap enforced (`jr/spend.json`); daily pulse is LLM-free.
- **Official APIs, rate-limited** — `gh`/GitHub + Composio + HTTP; no ToS-violating scraping.

---

## 8. Cadence & crons

| Report | Cron | Cost |
|---|---|---|
| **Afternoon pulse** (light, warning-gated) | new `jr-intel-pulse`, hourly ~12:00–18:00 BRT — **only delivers on a 🟡/🔴 warning** (⟨Q2⟩) | ~0 (no LLM) |
| **Weekly deep** | fold into existing `jr-telemetry` (Mon 09:07) | ≤ cap |

Neither unpauses `jr-daily`. The intel report is a distinct, read-only lane.

---

## 9. Open questions ⟨Q⟩

- **⟨Q1⟩** Which repos are "catalogued firmware" for S2 — derive from the atlas's firmware
  records' `github` field automatically? (Assumed yes.)
- **⟨Q2⟩ RESOLVED (2026-08-31):** pulse runs *all afternoon* (recurring), and **only pings
  when there's a 🟡/🔴 warning** — never an "all green" message. Silent unless it must warn.
- **⟨Q3⟩** Our-repo bad-data reports (S3) — auto-open a tracking Issue, or just warn you?
- **⟨Q4⟩** Manufacturer watch (S7) — in scope now, or defer until S2–S6 prove out?

---

## 10. Non-goals

- Not an authoring system — it warns; it never writes the atlas or opens content PRs.
- Not an LLM-driven analyst — deterministic fetch+classify; LLM only rephrases, under cap.
- Does not unpause `jr-daily`.
