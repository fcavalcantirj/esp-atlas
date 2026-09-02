# SPEC — Firmware popularity floor (drain quality gate)

> Jr's launcher drain currently has **no minimum-popularity floor**, so obscure projects
> (e.g. `server-vampeta`: 3 stars, 0 forks) slip in when a batch is thin. This adds a floor so
> the catalog carries firmware that is **actually used or actually built-on — never filler.**
> (Felipe, 2026-09-02.)
>
> **2026-09-02 update:** downloads are DROPPED entirely as a popularity signal. A
> launcher/M5Burner download count is not a citable, stable metric — it was never fetched from a
> source of record the way GitHub stars/forks are. The floor is now **GitHub stars OR forks
> only**, and downloads are never fetched, stored, or consulted anywhere in the pipeline.

## The floor
A candidate is authored only if it clears **either** GitHub signal (OR-gated — forks are a
stronger "actually built-on" signal than stars, so a heavily-forked but under-starred utility
still clears):

- **GitHub stars ≥ `STAR_FLOOR`**, **OR**
- **GitHub forks ≥ `FORK_FLOOR`**

Below **both** → the drain **skips** it (records it as `seen`/uncitable-popularity in the ledger,
so it isn't re-fetched every run) and reports it. Never author sub-floor firmware.

**Starting constants (tunable in one place):**
- `STAR_FLOOR = 25`
- `FORK_FLOOR = 25`

These live as module constants in `jr/scorer.py` (`clears_popularity_floor(stars, forks)`),
mirrored by hand in `scripts/firmware_floor_audit.py` (jr/ is a standalone package with its own
venv, not importable from the repo-root scripts runtime).

## Interaction with existing signals
- Complements `rank_juicy` (launcher-download × stars ordering, unchanged) — ranking still picks
  the *best* candidate to author from an already-floor-cleared pool; the floor removes the
  *unworthy* before ranking ever runs. Ranking is a prioritization concern, not a popularity
  gate, so it is untouched by this change.
- Complements the demand-steer: a candidate that clears the floor **or** matches high GSC demand
  is worth authoring; pure filler (low stars, low forks, no demand) is not.

## Exemptions
The floor gates **drain-authored** firmware only. **Human-curated / known-good** entries
(trust tier above `unverified`, or hand-added like `bruce`, `esp32marauder`, `rogueduck`) are
**exempt** — a maintainer chose them deliberately; popularity doesn't override human curation.
The allowlist lives as `CURATED_EXEMPT` in `scripts/firmware_floor_audit.py`.

## Pruned the existing sub-floor entries (done 2026-09-02)
Every catalogued firmware below **both** floors (stars<25 AND forks<25) and not
human-curated/known-good was removed, along with its `data/recipes/<board>__<id>/` pairing(s):
37 entries (`rogueduck`, at 4 stars / 0 forks, was kept — it's on `CURATED_EXEMPT`).

## Persisted, TIMESTAMPED popularity (so CI can enforce the floor with no LLM, no network)
The drain knows stars + forks at author time; discarding them would mean nothing downstream
could verify the floor offline. Fix — store the numbers, dated like a citation (popularity
drifts):
- On author, write a `popularity` block into the firmware frontmatter:
  ```
  popularity:
    stars: <github stargazers_count>
    forks: <github forks_count>
    as_of: <YYYY-MM-DD>   # snapshot date — popularity changes, so it is dated and refreshable
  ```
  Cite it (GitHub API) in `sources`. The `as_of` date makes it a freshness-aware snapshot a
  future Jr "popularity refresh" job can re-measure (keep-true). Downloads are **never** written
  here — `scripts/strip_downloads.py` is the one-off migration that removed the stale
  `downloads:` line (and any `downloads`-only source citation) from every existing entry.
- Schema: the optional `popularity` object in `schema/firmware.schema.json` still declares a
  `downloads` property for backward JSON-Schema compatibility with old data, but nothing in the
  pipeline writes it anymore — it is dead going forward.
- Backfill: `scripts/popularity_backfill.py` stamps `popularity{stars, forks, as_of}` (one live
  `gh api repos/<owner>/<repo>` call per unstamped entry — `stargazers_count` + `forks_count`) onto
  pre-existing unstamped firmware so the gate has data for today's catalog.

## CI + validation floor gate (deterministic, mechanical — no LLM, no manual curation)
- `scripts/firmware_floor_audit.py` reads the **stored** `popularity` (not a live fetch) → fully
  offline/deterministic. `.github/workflows/validate.yml` runs it with `--ci`: **exits non-zero
  (fails the build)** if any firmware is below **both** floors (stars < STAR_FLOOR AND
  forks < FORK_FLOOR) and not curated-exempt.
- `scripts/validate.py` (the same script CI's `schema` job runs first) ALSO mechanically enforces
  the floor via `check_popularity_floor()`, which reuses `firmware_floor_audit.audit()` — so the
  floor is a validation-time gate, not only a drain-time or CI-only one. `python3
  scripts/validate.py` fails with the offending firmware id(s) printed if anything regresses
  below the floor.
- Effect: GitHub **blocks the merge** of any sub-floor firmware, mechanically, at two independent
  checkpoints. Felipe never hand-curates for popularity again.

## Order of work (Felipe: "one after another, after spec")
1. **This spec.** ✓
2. **Audit + prune** existing sub-floor firmware (server-vampeta + the swept list). ✓
3. **Build the floor** into the drain (TDD: sub-floor candidate skipped; above-either-floor
   authored; curated exempt). ✓
4. **Drop downloads entirely** (2026-09-02): removed from the floor decision, from storage, and
   from every existing firmware's `popularity` block; the floor is stars-or-forks only, mechanically
   re-checked by `scripts/validate.py`. ✓
