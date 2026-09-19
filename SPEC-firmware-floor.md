# SPEC — Firmware popularity floor (drain quality gate)

> Jr's launcher drain currently has **no minimum-popularity floor**, so obscure projects
> (e.g. `server-vampeta`: 3 stars, 0 forks) slip in when a batch is thin. This adds a floor so
> the catalog carries firmware that is **actually used or actually searched-for — never filler.**
> (Felipe, 2026-09-02.)

## The floor
A candidate is authored only if it clears **any one** of three signals (OR-gated — a star is a
bookmark, a fork is a derivative, so a heavily-forked but under-starred utility still earns its
place; and GitHub stars are not the only evidence a project is real and used):

- **GitHub stars ≥ `STAR_FLOOR`**, **OR**
- **GitHub forks ≥ `FORK_FLOOR`**, **OR**
- **An independent editorial home** — the repo's `homepage` is a real project site/blog, not the
  repo itself and not a GitHub Pages mirror of it (see "Editorial home" below).

Below **all three** → the drain **skips** it (records it `seen` in the ledger, so it isn't
re-fetched every run) and reports it. Never author sub-floor filler.

**Constants:**
- `STAR_FLOOR = 25`
- `FORK_FLOOR = 25`

### Editorial home (the third signal)
GitHub stars are not the same as notability. Real, niche firmware can have a genuine independent
write-up — a maintainer's blog, a project homepage — while sitting on a handful of stars: **the
RogueDuck class**. `rogueduck` (a Cardputer pentest tool) has 6 stars and under 25 forks, but a
real, independently-run homepage at `ethicalhackersden.org`. A stars/forks-only bar wrongly cuts
it; a genuine external write-up is evidence a project is actually in use that a star count alone
misses.

`clears_popularity_floor(stars, forks, homepage=None)` (`apps/core/src/esp_atlas_core/floor.py`)
treats `homepage` as editorial evidence only when it is a non-empty `http(s)` URL whose host is
**neither** `github.com` **nor** any `*.github.io` domain — those name the repo itself or a
GitHub Pages mirror of it, not an independent home. This is deterministic string/host matching on
a URL already returned by the GitHub API (`fetch_github_repo`'s `homepage` field) — **zero LLM**,
same as every other floor check.

The third signal only ever **widens** what clears; it never narrows it. Filler with no homepage —
`server-vampeta`: 3 stars, 0 forks, `homepage: None` — is completely unaffected and still cut,
same as before this signal existed.

`homepage` is not part of the STORED `popularity` snapshot (see below), so it is consulted **live**
at admission time (`jr/stage_admit.py`, `jr/drain.py`) and re-checked live by the PR guard
(`scripts/jr_pr_guard.py`) — never by the offline audit (`scripts/firmware_floor_audit.py`), which
only ever sees whatever stars/forks were stamped at author time.

**Downloads are NOT a metric — anywhere.** *(Superseded 2026-09-03; an earlier revision of this
spec gated on launcher/M5Burner `downloads ≥ 500`.)* The launcher's download count is not a
citable popularity signal: it is self-reported by a third-party catalog, it counts installs of
someone else's re-upload rather than of the project, and `seeds.json` already marks that catalog
**discovery-only, never to be bulk-ingested**. It survives solely as a tie-breaker inside
`rank_juicy` ordering, never as a gate, and the `downloads` key is removed from `firmware.md`
records by `scripts/strip_downloads.py`.

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
  build)** if any firmware is below **both** floors (stars < `STAR_FLOOR` AND forks <
  `FORK_FLOOR`) and not curated-exempt.
- Effect: GitHub **blocks the merge** of any sub-floor firmware, mechanically. Felipe never
  hand-curates for popularity again.

## Order of work (Felipe: "one after another, after spec")
1. **This spec.** ✓
2. **Audit + prune** existing sub-floor firmware (server-vampeta + the swept list).
3. **Build the floor** into the drain (TDD: sub-floor candidate skipped; above-either-floor
   authored; curated exempt).
