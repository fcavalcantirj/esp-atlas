# SPEC — Firmware popularity floor (drain quality gate)

> Jr's launcher drain currently has **no minimum-popularity floor**, so obscure projects
> (e.g. `server-vampeta`: 3 stars, 0 forks) slip in when a batch is thin. This adds a floor so
> the catalog carries firmware that is **actually used or actually searched-for — never filler.**
> (Felipe, 2026-09-02.)

## The floor
A candidate is authored only if it clears **either** signal (both criteria, OR-gated — because
Cardputer firmware often has low GitHub stars but real M5Burner *downloads*):

- **GitHub stars ≥ `STAR_FLOOR`**, **OR**
- **launcher/M5Burner downloads ≥ `DOWNLOAD_FLOOR`**

Below **both** → the drain **skips** it (records it as `seen`/uncitable-popularity in the ledger,
so it isn't re-fetched every run) and reports it. Never author sub-floor firmware.

**Starting constants (tunable in one place):**
- `STAR_FLOOR = 25`
- `DOWNLOAD_FLOOR = 500`

These live as module constants in `jr/scorer.py` (or `jr/drain.py`) so the bar is one edit.

## Interaction with existing signals
- Complements `rank_juicy` (downloads × stars ordering) — ranking picks the *best*; the floor
  removes the *unworthy*. Both apply.
- Complements the demand-steer: a candidate that clears the floor **or** matches high GSC demand
  is worth authoring; pure filler (low stars, low downloads, no demand) is not.

## Exemptions
The floor gates **drain-authored** firmware only. **Human-curated / known-good** entries
(trust tier above `unverified`, or hand-added like `bruce`, `esp32marauder`) are **exempt** —
a maintainer chose them deliberately; popularity doesn't override human curation.

## Prune the existing sub-floor entries
One-off audit + prune (done *before* the drain change lands):
1. List every catalogued firmware below **both** floors AND not human-curated/known-good.
2. Present the list; prune the clear filler (`server-vampeta` first).
3. Keep anything with a real reason (board-specific, cited, or curated) even if low-pop —
   note why.

## Persisted, TIMESTAMPED popularity (so CI can enforce the floor with no LLM, no network)
The drain knows stars + downloads at author time but discards them, so nothing downstream can
verify the floor offline (this is why the audit went blind on Sun-Rider: 12 stars but 6,087
downloads). Fix — store the numbers, dated like a citation (popularity drifts):
- On author, write a `popularity` block into the firmware frontmatter:
  ```
  popularity:
    stars: <github stargazers_count>
    downloads: <launcher / M5Burner download count>
    as_of: <YYYY-MM-DD>   # snapshot date — popularity changes, so it is dated and refreshable
  ```
  Cite it (GitHub API + launcher catalog) in `sources`. The `as_of` date makes it a
  freshness-aware snapshot a future Jr "popularity refresh" job can re-measure (keep-true).
- Schema: add the optional `popularity` object to `schema/firmware.schema.json`.
- Backfill: a one-off pass stamps `popularity` onto existing firmware (fetch live once) so the
  gate has data for today's catalog.

## CI floor gate (deterministic, mechanical — no LLM, no manual curation)
- `scripts/firmware_floor_audit.py` reads the **stored** `popularity` (not a live fetch) → fully
  offline/deterministic.
- Add a step to `.github/workflows/validate.yml`: run the audit and **exit non-zero (fail the
  build)** if any firmware is below **both** floors (stars < STAR_FLOOR AND downloads <
  DOWNLOAD_FLOOR) and not curated-exempt.
- Effect: GitHub **blocks the merge** of any sub-floor firmware, mechanically. Felipe never
  hand-curates for popularity again.

## Order of work (Felipe: "one after another, after spec")
1. **This spec.** ✓
2. **Audit + prune** existing sub-floor firmware (server-vampeta + the swept list).
3. **Build the floor** into the drain (TDD: sub-floor candidate skipped; above-either-floor
   authored; curated exempt).
