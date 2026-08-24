# SPEC — home explorer: the intent-first front door

> Status: DRAFT (living). Reframes the esp-atlas home from a spec-picker into an
> intent-first, self-feeding front door + flashing hub. Extends `SPEC.md`
> governance and `SPEC-wizard.md` (flash bridge). No build until this is agreed.

## 1. Vision
Nobody lands on esp-atlas knowing they need "8 MB PSRAM." They land knowing
**what they want to do** — *run Marauder, build a badge with a screen, host a
web UI, play games.* The home should answer **intent**, not demand specs.

Three principles:
- **Intent over specs.** The headline asks *"what are you building / what do you
  want to run?"* Memory/RF/spec filters demote to **Advanced**. Every intent
  resolves to a **ranked board list + the reason each matched.**
- **Alive by construction.** Every option is a projection of data + live signal.
  Add a firmware → a chip appears. It *cannot* go stale.
- **Closes the loop.** intent → board → *why* → recipe → **flash right here.**
  esp-atlas is where you decide AND do it.

## 2. Home layout — intent-first (LOCKED 2026-08-24, mockup-approved)
Diagnosis of the old home: it led with cold spec dropdowns (form factor / budget /
jargon checkboxes) on the left and left a dead void on the right. **Inverted.** Top
to bottom:

| Order | Block | Role |
|---|---|---|
| 1 | **Hero** — "What do you want to build?" (copy swappable) | Sets the intent framing. |
| 2 | **Intent door** — one prompt: *"Tell me what you want to build or run…"* + "…or tap an idea below" | The soft entry. Phase 1 → search/examples; Phase 2 → Groq intent→filters (Newcomer Wizard). |
| 3 | **Rich examples grid** — fills the page; generated, not static | Three soft groups: **Run a firmware** (recipe-graph), **Build a project** (capability filters), **Just show me** (discovery). Each card carries the reason/count. This is §3b. |
| 4 | **Spec wizard — DEMOTED, not deleted** | A lean drawer "Spec wizard · Open ›" that **expands the full filter panel inline** (collapsed by default). The top-nav **"Wizard" link routes to a full `/wizard` page** (the old left-panel layout relocated there). Reachable two ways; never the cold front. |
| — | **Search** stays accessible (nav / lightweight bar). | knows the part or term |

**Rulings:** memory/RF/USB/mesh specifics live in the wizard's Advanced (unchanged);
the "Runs a web server" intent toggle stays top-level in the wizard (SPEC-INDEX C4).
The wizard is **demoted + relocated, not removed** — full page at `/wizard`, quick
inline expand on the home.

This spec is mostly about **§3b** (the examples) + the Newcomer Wizard (§3) + the
**flash hub** it opens onto.

## 3. The easy wizard for newcomers — classic → Groq prompt (scales FLAT)
A newcomer can't answer "form factor" or "native USB." So the specifics
(form/mesh/USB/memory) demote to **Advanced**, and the easy path is two phases:

- **Phase 1 — classic wizard, simplified.** A few plain-language questions mapped
  1:1 to real fields. Answer what matters, skip the rest. Pure filters — zero
  inference, scales to thousands of boards free.
- **Phase 2 — the prompt (Groq, reasoning).** A ChatGPT-style box: type intent in
  your own words → Groq parses it into **structured filters** (+ the *why*). The
  filters then run over the catalog.

**The cost principle (locked): Groq reads the QUERY, not the catalog.**
`"watch my plants"` → `{low_power, battery, sensor}` is the *same one cheap call*
whether we have 95 boards or 5,000 — board count never touches the Groq bill.
Filtering hundreds/thousands is trivial (SQLite scales to millions). **Cache by
query string** → each phrasing costs one call ever; popular ones free after first
hit. So cost is per-unique-query and **flat in catalog size.** No fine-tuning (wrong
tool for a live dataset); if we want typo-tolerant/semantic match later, precompute
embeddings at build and cosine-match at the edge — still no runtime LLM.

## 3b. "Start with a question" — the alive examples (§3's clickable suggestions)
No hardcoded list, no taxonomy, no editorial "best of." The examples are
**alive** — `f(data, signal, analytics)`:
- **Sourced from N places:** our recipe graph (a real "Run &lt;firmware&gt;" per
  firmware) + external signal (awesome-esp32 lists, new firmware releases, trending
  r/esp32) authored by the **discovery adapter pack** (see `SPEC-discovery.md`).
- **Ordered smartly:** by click-analytics (what people actually pick) + trending.
  Cold-start = neutral order until data accrues.
- **Optional zero-inference entry: domain buckets** — *IoT · Gardening/sensors ·
  Pentest/hacking · Prototyping & DIY · Wearables · Screens/badges* — each a saved
  query into real data (pentest = runs Marauder/Bruce; gardening = low-power +
  battery + sensor pins). Honest mappings to real fields, **not our opinions.**
- Every example resolves to a **ranked list + the reason each matched.**

## 4. Ranking + the "why" (shared everywhere)
Every intent returns a **ranked** list where each board carries a one-line
**reason it matched** ("8 MB PSRAM → many concurrent clients · 16 MB flash →
room for assets · runs Bruce via keyboard+screen"). Reasons are derived from real
fields — never generated prose. This is the teaching layer.

## 5. Live signal + analytics (the "smart, self-feeding" part)
This section **consumes** the oracle-loop; it does not define it (see `SPEC-INDEX.md`).
- **External signal** is authored by the **discovery adapter pack**
  (`SPEC-discovery.md`) — awesome-esp32, new firmware releases, trending r/esp32 →
  cited, human-merged records. This spec only **surfaces** them.
- **Click analytics:** order examples by what users actually click; cold-start =
  neutral order. ⚠ Global click-analytics needs a runtime store — an open
  architecture decision vs SPEC.md's "no database" (see `SPEC-INDEX.md` §4). Does
  not block L1/L2.

## 6. The flashing HUB (the differentiator)
Almost no site crosses **all** the flashers. esp-atlas does:
- **Matrix view:** every firmware × every board it runs (the recipe graph as a
  browsable grid). "What can this board run?" and "What runs this firmware?" both
  answerable in one view.
- **Flash right here — bridge, not host.** Reuse `SPEC-wizard.md`: ESP Web Tools
  in-browser for CORS-open hosts; SSRF-allowlisted streaming proxy for the rest.
  **We never rehost binaries** — we transit/cite the project's own releases.
- Position: esp-atlas = **the hub for awesome ESP32 stuff**, the one place to
  discover a board, understand *why*, and flash it — without leaving.

## 7. Data this needs (the "improve data" track)
- **Firmware tags/categories** on each firmware record (`pentest`, `games`,
  `iot`, `home-automation`, `dev-tool`) → powers Shelf A grouping + Shelf B.
- **Add Bruce** firmware + recipes (sourced). Then more: WLED, Meshtastic, ESPHome, a game.
- **Structure `display`** (25 boards, field exists but unfaceted) + **SD-slot** (12, prose).
- Keep growing the board roster.

## 8. Build layers (each independently shippable)
1. **L1 — dynamic presets from OUR data:** replace the static `PRESETS` array with
   generated shelves (Shelf A from recipes; Shelf B/C from fields). Lights up today.
2. **L2 — flash-matrix hub:** the firmware×board grid + flash-right-here bridge.
3. **L3 — live + smart:** click-analytics ranking + the external-signal cron.

## 9. Constraints / honesty (non-negotiable)
- No dead intents: every chip resolves to ≥1 board (oracle invariant, like the
  wizard's "no dead options").
- No faked signal: trending/new always cites source + date.
- No rehosting: flashing is a bridge to the project's own binaries.
- CI-gated: schema + oracle + live-sources green before anything ships.

## 10. Decisions locked (this session)
- Specifics (form/mesh/USB/memory) → **Advanced**. Easy path = plain questions.
- Newcomer flow: **classic simplified wizard → Groq reasoning prompt.** Groq reads
  the query, not the catalog → cost flat in board count; cache by query string.
- No fine-tuning on the yaml (wrong tool for live data).
- §3 examples are **alive** (N sources, smart order by clicks/trending), **no
  editorial rankings** — buckets/examples map to real fields only.
- Flash "matrix" is just the **firmware page**, not a new artifact.

## 11. Still open
- Exact plain-language questions in the simplified classic wizard (each must map
  to a real field).
- Which Groq model + the prompt/JSON-schema contract for intent→filters.
- Domain-bucket final list + each bucket's underlying query.
