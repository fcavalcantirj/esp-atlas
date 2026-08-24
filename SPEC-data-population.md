# SPEC — agent-driven data population (78 → hundreds)

> Status: DRAFT. How esp-atlas scales its catalog from ~78 boards to hundreds using
> sourced, CI-gated agents — WITHOUT lowering the cite-or-omit bar. Extends `SPEC.md`
> governance and reuses `SPEC-freshness.md`'s detect→propose→gate machinery.
> Population = the freshness loop's **detect stage run WIDE + agents authoring each
> record.** Same rails, proactive instead of maintenance.

## 1. Why a spec (not just "run agents")
"Hundreds of boards" is only valuable if every record is **real, cited, and
schema-valid.** Hundreds of stale guesses is a liability, not an asset. The whole
point of esp-atlas is trust; mass population must *strengthen* the citation-audit
bar, never bypass it. This spec makes population a governed pipeline, not a scrape.

## 2. What gets populated
| Entity | Source of truth (official-first) | Notes |
|---|---|---|
| **board** | Arduino `package_<vendor>_index.json` + `boards.txt`, Launcher supported-devices wiki, M5Burner API, vendor product/spec pages | the bulk of the work |
| **module** | Espressif + vendor module datasheets | flash/psram/antenna/certs |
| **soc** | Espressif product line + datasheets | rare, ~finite set |
| **brand** | vendor homepage | auto-created per `data/boards/<brand>/` folder; not a queryable part |
| firmware / recipe | (owned by `SPEC-freshness.md`) | referenced, not re-specced here |

## 3. Pipeline — discover → fan-out → author → gate
1. **Discover the universe.** Per-vendor adapters enumerate every candidate part
   from official machine-readable catalogs (the same adapters freshness uses).
   Output: a worklist of parts **not yet in the repo** (dedup by id/slug — idempotent).
2. **Fan-out authoring agents.** One delegate per candidate record. Each agent:
   - Reads the authoritative source(s) for that exact part.
   - Writes schema-valid frontmatter, **cite-or-omit** — every hard spec carries a
     `sources:` entry with a live URL + `verified` date; unverifiable fields are
     **omitted, never guessed** (matches the memory-fill run's discipline).
   - Auto-creates the `brand` record if the vendor folder is new.
3. **Gate — the locked pipeline, unchanged.** Each record lands on a branch → **PR**
   → CI (`schema` + `sources-live` + oracle/`tests`, incl. no-orphan-firmware) → a
   **human merges.** Bot never writes `main`.
4. **Trust tier.** Auto-authored records land conservative; any compatibility/
   trust-tier claim is **human-promoted only, forever** (inherited from freshness).

## 4. Scale mechanics (what makes 78→hundreds safe)
- **Idempotent + dedup:** never re-create an existing part; re-authoring an existing
  record updates its PR, never duplicates (inherited).
- **Batched by vendor**, bounded parallel agents, cost-capped per batch. Each batch
  is a reviewable PR set, not one giant unreviewable dump.
- **Coverage report per batch:** N discovered, N authored, N still-unknown (with
  why), field-fill rates — the same measured-not-claimed reporting as the memory fill.
- **No orphans:** every `firmware` keeps ≥1 `recipe` (existing CI rule); population
  never introduces dangling refs.

## 5. Quality invariants (CI-enforced, non-negotiable)
1. Schema-valid or it doesn't merge.
2. Every hard spec cited to a **live** source (`sources-live`), else omitted.
3. Oracle green (no dead wizard options introduced by new data).
4. No guessed numbers — `psram_mb: 0` etc. only when the source says so explicitly.
5. Human merges every PR. Agents propose; humans dispose.

## 6. Relationship to the other specs
- **`SPEC-freshness.md`** keeps populated records live (daily). Population seeds;
  freshness maintains. **Same adapters, same gate.**
- **`SPEC-home-explorer.md`** consumes the result: more boards → the wizard/Groq
  prompt and the alive examples get richer automatically (cost stays flat — Groq
  reads the query, not the catalog).

## 7. Open questions
- Vendor batch order (start with the highest-signal official indexes — Espressif,
  Adafruit, M5Stack, LilyGO, SparkFun?).
- Target for a first population wave (e.g. every board in the Arduino vendor indexes
  we already trust) and its cost envelope.
- One agent per board vs one agent per vendor-batch (fan-out granularity vs cost).
