# SPEC — Firmware popularity floor (drain quality gate)

> Jr's launcher drain currently has **no minimum-popularity floor**, so obscure projects
> (e.g. `server-vampeta`: 3 stars, 0 forks) slip in when a batch is thin. This adds a floor so
> the catalog carries firmware that is **actually used or actually searched-for — never filler.**
> (Felipe, 2026-09-02.)

## The floor
A candidate is authored only if it clears **any one** of four signals (OR-gated — a star is a
bookmark, a fork is a derivative, so a heavily-forked but under-starred utility still earns its
place; and GitHub stars are not the only evidence a project is real and used):

- **GitHub stars ≥ `STAR_FLOOR`**, **OR**
- **GitHub forks ≥ `FORK_FLOOR`**, **OR**
- **An independent editorial home** — the repo's `homepage` is a real project site/blog, not the
  repo itself and not a GitHub Pages mirror of it (see "Editorial home" below), **OR**
- **Launcher/M5Burner downloads ≥ `DOWNLOAD_FLOOR`** — see "The fourth signal: launcher
  downloads" below.

Below **all four** → the drain **skips** it (records it `seen` in the ledger, so it isn't
re-fetched every run) and reports it. Never author sub-floor filler.

**Constants:**
- `STAR_FLOOR = 25`
- `FORK_FLOOR = 25`
- `DOWNLOAD_FLOOR = 2000`

### Editorial home (the third signal)
GitHub stars are not the same as notability. Real, niche firmware can have a genuine independent
write-up — a maintainer's blog, a project homepage — while sitting on a handful of stars: **the
RogueDuck class**. `rogueduck` (a Cardputer pentest tool) has 6 stars and under 25 forks, but a
real, independently-run homepage at `ethicalhackersden.org`. A stars/forks-only bar wrongly cuts
it; a genuine external write-up is evidence a project is actually in use that a star count alone
misses.

`clears_popularity_floor(stars, forks, homepage=None, downloads=None)` (`apps/core/src/esp_atlas_core/floor.py`)
treats `homepage` as editorial evidence only when it is a non-empty `http(s)` URL whose host is
**neither** `github.com` **nor** any `*.github.io` domain — those name the repo itself or a
GitHub Pages mirror of it, not an independent home. This is deterministic string/host matching on
a URL already returned by the GitHub API (`fetch_github_repo`'s `homepage` field) — **zero LLM**,
same as every other floor check.

The third signal only ever **widens** what clears; it never narrows it. Filler with no homepage —
`server-vampeta`: 3 stars, 0 forks, `homepage: None` — is completely unaffected and still cut,
same as before this signal existed.

`homepage` is consulted **live** at admission time (`jr/stage_admit.py`, `jr/drain.py`) and
re-checked live by the PR guard (`scripts/jr_pr_guard.py`). **Persistence is mandatory here too,
same as downloads below**: a candidate admitted *only* because its live homepage cleared
`is_editorial_home()` must have that fact STAMPED into the record — `popularity.editorial_home`,
the homepage URL itself — or the offline audit (`scripts/firmware_floor_audit.py`, which never
fetches live) would see only stars/forks/downloads, flag the record below-floor on the very next
tick, and the per-tick guard would discard the whole worktree before it ever merges — silently
re-discovering and re-rejecting the same candidate forever. (This was exactly the bug, fixed
2026-10-08: the stamp closes it the same way `popularity.downloads` closes the download signal's
own live/offline gap.) `jr/tools.py`'s `author_firmware_and_recipes` and `jr/stage_admit.py`'s
admit write both stamp `editorial_home` — only when `is_editorial_home()` actually clears, never
a plain github.com/github.io homepage — and `scripts/firmware_floor_audit.py` reads it back as
the `homepage` argument to the SAME `clears_popularity_floor()`, so admission and the offline
gate can never hand-drift apart on this signal either.

### The fourth signal: launcher downloads
*(Removed 2026-09-04 on the grounds that a launcher/M5Burner download count is self-reported by
a third-party catalog and not a citable signal; RESTORED 2026-10-06, Felipe: the stars/forks/
editorial-home bar was rejecting the catalog's most-installed community firmware.)*

A stars/forks/editorial-home-only floor rejects exactly the firmware real users install most:

| Firmware | Launcher downloads | GitHub stars | Would clear stars/forks/editorial-home alone? |
|---|---|---|---|
| M5Launcher | 120,000 | 1 | No |
| Evil-Cardputer | 92,000 | 1 | No |
| Doom-for-Cardputer | 37,000 | 1 | No |

Each sits under 25 stars because installing it from a launcher catalog never requires visiting
its GitHub page — a star count measures GitHub engagement, not installs. A download count this
high is not noise; it is the single strongest "real people are actually running this" signal the
catalog has — stronger than a star, which a repo's own author can rack up in an afternoon.
`DOWNLOAD_FLOOR = 2000` sits far enough above a trivially gamed number (a handful of friends
clicking install) that clearing it is proof of real, widespread use, not a rescue for every
low-star repo — only the ones genuinely in people's hands.

**Persistence is mandatory, not optional.** Downloads are a launcher-catalog signal, not a
GitHub one: there is no live endpoint that reports them, so a guard checking a record LIVE
(`scripts/jr_pr_guard.py`) or OFFLINE (`scripts/g2_guard.py`, `scripts/firmware_floor_audit.py`)
can only ever see a download count that was stamped onto the record at author time. A record
that clears the floor *only* on downloads and does NOT persist `popularity.downloads` would
look sub-floor to every guard that re-checks it later — exactly the failure this fixes. So:

- `jr/writers.py`'s `render_firmware` and `jr/tools.py`'s `author_firmware_and_recipes` both
  write `popularity.downloads` (alongside `stars`/`forks`/`as_of`) whenever a download count is
  known at author time — never invented, same cite-or-omit discipline as the other two numbers.
- `jr/drain.py` (the only admission path with a launcher download count — topic-admit via
  `jr/stage_admit.py` has none, and passes `downloads=None` explicitly, no behavior change) reads
  it straight from the launcher-catalog entry (`entry["download"]`) and threads it through both
  the floor check and authoring.
- Every guard that re-verifies the floor — `scripts/jr_pr_guard.py` (live GitHub re-check, which
  has no download field to re-fetch so it reads the record's STORED `popularity.downloads`),
  `scripts/g2_guard.py`, and `scripts/firmware_floor_audit.py` (both fully offline) — reads the
  same persisted number through the same `clears_popularity_floor()`, so none of them can
  disagree with admission about what qualifies.

It still contributes to `rank_juicy` ordering as before (downloads × stars combined); it is now
ALSO a gate, not only a tie-breaker.

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
    editorial_home: <the live homepage URL, only when it cleared is_editorial_home() at admission>
    as_of: <YYYY-MM-DD>   # snapshot date — popularity changes, so it is dated and refreshable
  ```
  Cite it (GitHub API + launcher catalog) in `sources`. The `as_of` date makes it a
  freshness-aware snapshot a future Jr "popularity refresh" job can re-measure (keep-true).
- Schema: add the optional `popularity` object to `schema/firmware.schema.json`.
- Backfill: a one-off pass stamps `popularity` onto existing firmware (fetch live once) so the
  gate has data for today's catalog.

### 2026-11-06: bounded GitHub count refresh

`jr/stage_popularity_refresh.py` runs in the existing hourly Jr tick. It groups the catalog
by bare GitHub owner/repository URL, excludes the known wrong Nyan URL until its separate cited
correction, and visits a deterministic slice of at most seven distinct repositories each hour.
At the current 144 eligible repositories, 24 hourly slots cover the catalog once per day when
ticks complete. A record with a GitHub observation less than 24 hours old is skipped. The tick
uses its existing counted GitHub-call and wall-clock budget; failed calls are not retried in
the same tick. A 404 skips only that repository; rate or transport failure stops the slice.

A response may replace the last-good snapshot only when `full_name` equals the record URL,
`id` is a positive integer matching any stored `popularity.github_repo_id`, and both
`stargazers_count` and `forks_count` are nonnegative integers (including real zero). Both
one-shot backfill writers also require the same exact name and positive stable ID; missing
data is skipped, never stamped as zero. On first observation the repository ID is persisted.
Real writes replace a file atomically in Jr's isolated worktree; its guard and CI validate the
staged result before publication. A true count that would put a non-exempt record below this
spec's floor is deferred for data review rather than aborting unrelated tick work.

`github_as_of` dates the GitHub counts; `downloads_as_of` and `editorial_home_as_of` are set
only when those signals were observed and cited by their own sources. Scheduled GitHub refresh
preserves launcher/home values and the legacy mixed-signal `as_of` without inferring a date
for either source. It adds or updates field-exact GitHub citations. A legacy source conflict or
any other change that would route to `jr-review` is deferred by the stage, including at the
open-review cap. The backend `/firmware` and `/examples` responses expose optional GitHub and
legacy dates so clients can label scope honestly.

This code is not operational proof: the first natural scheduled tick must provide its run ID,
source revision, upstream results, persisted counts and deployed readback. A page view must not
call GitHub without an atomic shared cross-instance coordinator and global rate budget; the
current regional Runtime Cache cannot provide either alone.

### On-view GitHub counts (backend contract, pending deployment proof)

`GET /api/firmware/{id}/popularity/live` is an optional, no-store detail-page read.
The handler loads the canonical firmware record; the client cannot supply a repository URL.
Only a bare `https://github.com/<owner>/<repo>` URL, a positive cited
`popularity.github_repo_id`, and a cited `popularity.github_as_of` date make a record
eligible. The response always includes `firmware_id`, `outcome` (`fresh`, `cached`,
`stale`, `unavailable`, or `ineligible`), `catalog` (GitHub stars/forks/date/source URL/
repository ID), `github` (validated live stars/forks/observation time/source URL/
repository ID, or null), and `retry_after_seconds` (or null). Counts of zero are valid;
missing counts are never converted to zero. The GitHub overlay is exposed only when
it is newer than the catalog's GitHub observation. It never changes the authored
catalog snapshot, sorting, recipe trust, or admission floor. The UI shows the source
and observation date and retains the cited catalog values on any failure.

The shared coordinator is one **read-write Postgres primary** (Neon through Vercel
Marketplace), not an eventually consistent read replica or per-instance memory.
Postgres [row locks](https://www.postgresql.org/docs/current/explicit-locking.html)
serialize competing claims on the singleton row; Neon's
[write path](https://neon.com/blog/wal-s3-lakebase-storage-for-the-era-of-agents)
acknowledges a transaction after quorum WAL persistence. The
[Vercel Marketplace integration](https://vercel.com/marketplace/neon) supplies a
Postgres resource, but no resource is provisioned for this feature yet.
Provisioning and migration are separate release gates. Every claim/publish/failure
transaction locks the precreated singleton budget row with `FOR UPDATE` before its
repository row, in that order. The claim checks a one-hour cache, one global in-flight
lease plus the per-repo lease, cooldowns and a conservative 20-reservation cap per UTC
hour. It uses the database clock for the hour boundary, leases, and cooldowns and
commits the reservation and random fencing token **before** GitHub is contacted. An
ambiguous or failed claim commit means no GitHub call. A lease lasts ten seconds;
the handler makes one GitHub request with `httpx.AsyncClient` inside an
`asyncio.timeout(5)` scope covering connect, response and complete bounded body read.
The request is never retried in the same page view.

The publish transaction requires both matching, unexpired global and repo lease
tokens, the same repository ID and full name, and complete nonnegative star/fork
counts before replacing the last-good cache. A failed/ambiguous publish returns the
preexisting last-good overlay or catalog, never `fresh`; a late response cannot
overwrite a newer lease. Successful cache is fresh for one hour and retained for
seven days as a stale fallback. HTTP 403/429 starts a global cooldown from valid
`Retry-After`/rate-reset headers, or at least 60 seconds without usable headers.
404/5xx/network failures keep the previous snapshot and set a per-repo backoff.
Missing/unavailable storage means no GitHub call. SQL and concurrent-instance,
lease-expiry, hour-boundary, identity, outage, cooldown, and failed-publish tests
are required before release. The feature is not live until the store, source-validated
ID coverage, page integration, and production page-triggered proof are reviewed.

## CI floor gate (deterministic, mechanical — no LLM, no manual curation)
- `scripts/firmware_floor_audit.py` reads the **stored** `popularity` (not a live fetch) → fully
  offline/deterministic.
- Add a step to `.github/workflows/validate.yml`: run the audit and **exit non-zero (fail the
  build)** if any firmware is below **every** floor (stars < `STAR_FLOOR` AND forks <
  `FORK_FLOOR` AND downloads < `DOWNLOAD_FLOOR`) and not curated-exempt.
- Effect: GitHub **blocks the merge** of any sub-floor firmware, mechanically. Felipe never
  hand-curates for popularity again.

## Order of work (Felipe: "one after another, after spec")
1. **This spec.** ✓
2. **Audit + prune** existing sub-floor firmware (server-vampeta + the swept list).
3. **Build the floor** into the drain (TDD: sub-floor candidate skipped; above-either-floor
   authored; curated exempt).
