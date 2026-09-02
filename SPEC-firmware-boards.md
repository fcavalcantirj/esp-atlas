# SPEC — Firmware board-support mapping (derive, don't guess)

> Status: **ROADMAP — NOT BUILT (2026-09-02, Felipe).** Defers to `SPEC-INDEX.md` on
> every ownership/vocabulary conflict. This spec exists because the catalog's single
> most load-bearing field — *which boards a firmware actually runs on* — is currently
> **guessed, not derived**, and nothing downstream can audit the guess.

## 0. Why this spec exists (the symptom Felipe hit)

Every firmware detail page under-reports compatibility: it shows **one board / one SoC**
when the firmware runs on **many** (e.g. `esp32marauder`, `bruce`, `ruview`). The
`firmware.socs` field is being set to a single value per repo — an LLM's one-shot guess
at drain time — instead of the firmware's real supported-board set.

Two failures compound it:

1. **No ground truth.** The board set is guessed from prose, not read from the repo's own
   build configuration (which *declares* every target).
2. **No provenance.** We store the guessed value with no source, so we cannot tell a
   correct mapping from a hallucinated one — offline or online.

**The RuView incident (motivating evidence).** `data/firmware/ruview` carried
`popularity.stars: 92336` yet was deleted by a manual *"remove 3 bad entries (manual
triage)"* commit — far above the `STAR_FLOOR = 25` in `SPEC-firmware-floor.md`, which
also **exempts** human-curated/known-good entries. Because no field carried provenance,
we could not answer the only question that mattered: **are those 92k stars real (→ a top
entry was wrongly purged) or fabricated (→ the record was garbage all along)?** The
inability to answer that, and a destructive triage that ran with no guard, is the disease
this spec treats. Guessing without proof, and deleting without a gate.

## 1. Principle: derive from the repo's own build signals — the LLM is the last resort

A firmware's supported boards are a **fact the source repo already declares** in
machine-readable form. Read it; do not infer it. Ranked by trust:

| Rank | Signal | What it yields | Determinism |
|---|---|---|---|
| 1 | **Release-asset filenames** (`*.bin` per board on GitHub Releases) | boards that actually ship a binary | deterministic |
| 2 | **`platformio.ini`** `[env:*]` `board = …` | one env per shipping variant | deterministic |
| 3 | **GitHub Actions build matrix** (`.github/workflows/*`) | every target the project CI builds | deterministic |
| 4 | **`boards.txt` / ESP-IDF `idf_component.yml` target** (Arduino/IDF projects) | declared chip/board targets | deterministic |
| 5 | **README compatibility table / prose** | boards named only in text | **LLM, constrained** |

Rules:
- Prefer the **highest-ranked signal present**; union across signals when several exist.
- The LLM (rank 5) is used **only** for prose the config does not cover, and its output is
  **validated against the canonical board universe** (§2) before it is written — a name
  that resolves to no known board is dropped, not stored.
- **Never** collapse a multi-board firmware to a single `soc`. The default is *many*.

## 2. Canonical board universe — ADOPT, do not rebuild (Pillar 1)

The set of ESP32 boards/chips that exist (board → SoC) is a **solved, external source of
truth**. esp-atlas grounds on it; it does not invent its own board list.

- **PlatformIO board registry** — `pio boards --json-output` → every board as JSON with
  its `mcu`/SoC, id, vendor. (`registry.platformio.org`)
- **`espressif/arduino-esp32/boards.txt`** — Espressif's official board↔chip definitions.
- **ESP Component Registry** (`components.espressif.com`) — official, per-target.
- Cross-reference only: **espboards.dev** (270 boards / 73 vendors / 6 chip families).

Derived board IDs from §1 are **resolved to canonical IDs here**. `SPEC.md` still owns the
`soc/module/board` entity model; this spec owns the *derivation + resolution* of a
firmware's board set, not the entity schema.

## 3. Provenance is mandatory — cite or omit (per field)

Every stored board claim carries where it came from, dated like popularity already is in
`SPEC-firmware-floor.md`:

```yaml
boards:
  - id: m5stack-cardputer          # resolved to canonical id (§2)
    source: platformio.ini         # signal rank (§1)
    url: https://github.com/…/blob/…/platformio.ini
    verified: '2026-09-02'
```

A board with no citable signal is **not written**. This is the same discipline the repo
already applies to `popularity` and to the discovery engine ("cited, code-backed,
human-merged — never a bot inventing hype", `SPEC-discovery.md` §1). It is what makes the
catalog auditable: any reader can trace a mapping back to the repo line that proves it.

## 4. Gates — nothing thin ships, nothing high-signal dies silently

Two hard gates, enforceable offline (no LLM, no network — the persisted signals in §1/§3
make this possible, same rationale as the floor spec's timestamped popularity):

- **G1 — completeness gate.** A firmware whose declared `boards` set is **narrower than its
  build signals imply** (e.g. `platformio.ini` lists 4 envs, record stores 1) **fails
  CI / is flagged for review**. Under-mapping can no longer pass silently.
- **G2 — destructive-operation guard.** No migration, prune, or triage may **delete** a
  firmware that clears a popularity/curation signal (floor-passing, human-curated, or
  cited high popularity) without an **explicit, logged override**. A step about to delete a
  92k-star entry must **refuse and surface it**, not proceed. (Direct fix for the RuView
  incident.)

## 5. Reliability doctrine (the rules every ingest/enrichment adapter obeys)

Distilled from how reliable autonomous data pipelines are actually built:

1. **Hybrid, never LLM-for-everything.** Deterministic parsing for machine-readable
   signals; the LLM only for genuine language interpretation. LLM-for-every-step is the
   named failure mode.
2. **Schema-valid ≠ true.** JSON-schema-constrained output guarantees *shape*, not
   *correctness* ("structured hallucination"). Validate meaning separately from form.
3. **Provenance per field** (§3).
4. **Quality gates that FAIL bad/incomplete rows** before they ship (§4) — the dbt /
   Great Expectations / Pandera pattern.
5. **Autonomous ≠ unsupervised.** Automate past human scale, but route low-confidence /
   destructive actions to a human (§4 G2). Freshness alone isn't quality — a repo with
   recent commits, one maintainer, no releases is *abandonment risk*, not "nice".

## 6. "Nice firmwares" — where curation lives (Pillar 3, mostly already specced)

Surfacing *good* firmware is owned by `SPEC-discovery.md` (awesome-esp32, GitHub
trending/releases, Reddit, HN — code-backed, human-merged) and gated by
`SPEC-firmware-floor.md` (stars **OR** downloads floor, human-curated exemptions). This
spec does **not** re-own that; it **strengthens** it with §3 provenance and §4 G2 so a
curated top entry can never be silently deleted, and so "nice" is judged on real, cited
popularity **and** maintenance/trajectory signals — not vibes.

## 7. Executor — this doctrine is Jr's mandate (unites with `SPEC-espatlas-jr.md`)

This spec is the *method*; **EspAtlas Jr. is the *doer***. Jr already owns the write lane
("keep 100% verified & verifiable — at scale, over time") and already declares this exact
problem in its §3b **Firmware coverage** rule — *"a firmware is not done at one recipe …
one board when the repo names several is a coverage gap Jr should close (Evil-M5Project →
Cardputer + AtomS3 + Core2)."* What Jr's spec lacks is **how** to read "what the repo
supports" and **enforcement** that the gap can't reship. This spec fills both. Mapping:

| This spec | Runs inside Jr as |
|---|---|
| §1 derive board set (release assets, `platformio.ini`, CI matrix, `boards.txt`) | the **launcherhub backlog-drain** (authoring) + **recipe/compat-drift** job — which already reads *"release `.bin` names, README device lists"*; this spec makes that reading explicit and ranked |
| §1 re-derive over time | the **pin&io / firmware re-check** off the staleness queue — closes the §3a *firmware · VERIFY* cell |
| §2 resolve to canonical board IDs | Jr's **board-population** signals (`boards.txt`, Arduino index) as the ID authority |
| §3 provenance per board (`source`/`url`/`verified`) | Jr's **cite-or-omit motto** (§2.1/2.2); validates in `validate.py` exactly like `popularity` already does |
| §4 G1 completeness gate + G2 destructive-op guard | Jr's **deterministic guard** (§2.6, `validate.py` + `check_sources_live.py`, **zero-LLM**) — so both gates are enforced on every PR and in CI, model-agnostic |
| restore/fix a mis-mapped or wrongly-purged entry | a **cited PR, human-merged** (Jr never writes `main`, §2.3) — never a silent edit |

**Two consequences worth stating loudly:**
- **G2 lives in Jr's PRUNE verb.** Jr's Liveness job is the only thing that deletes; G2
  makes it **refuse to prune a floor-passing / human-curated / high-popularity firmware
  without an explicit logged override**. The RuView-style silent purge becomes impossible
  by construction, because the guard that blocks it is the same zero-LLM guard Jr already
  cannot override.
- **The motto already demands provenance; this spec just applies it to the board field.**
  Nothing new philosophically — it closes the one field (`boards`) that was being written
  without a citation while everything else (`popularity`, pins, specs) already is.

Ownership: `SPEC-espatlas-jr.md` owns the crons, guard, memory, and PR pipeline;
**this spec owns the firmware→board derivation method and the two gate definitions.** On
any conflict, `SPEC-INDEX.md` wins.

## 8. Non-goals

- **Not** rebuilding the board universe (§2 is adopted, not authored).
- **Not** inventing compatibility not evidenced in the source repo — absence of a signal
  means *omit*, never *fabricate*.
- **Not** changing the `soc/module/board` entity model (`SPEC.md`) or the flash flow
  (`SPEC-wizard.md`) — this is purely how the firmware→board set is derived, cited, gated.

## 9. References

Internal: `SPEC-espatlas-jr.md` (the executor — crons, guard, PR pipeline) ·
`SPEC-INDEX.md` (arbiter) · `SPEC.md` (entity model) · `SPEC-firmware-floor.md`
(popularity floor + timestamped popularity) · `SPEC-discovery.md` (community sourcing) ·
`SPEC-data-population.md` (official seeding) · `SPEC-wizard.md` (firmware entity/flash).

External sources of truth: PlatformIO board registry (`pio boards --json-output`) ·
`espressif/arduino-esp32/boards.txt` · ESP Component Registry · GitHub Search API
(`stars:`/`forks:`/`pushed:` for popularity + maintenance) · awesome-esp32 lists.

Method grounding (reliable autonomous data population): hybrid LLM+deterministic ETL,
constrained-decoding limits, Wikidata per-statement provenance, dbt/Great
Expectations/Pandera quality gates, GitHub repo-trajectory (growing/stable/declining/
collapsing) risk classification.
