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
call GitHub. A live stale-while-revalidate endpoint remains dependent on an atomic shared
cross-instance coordinator and global rate budget; the current regional Runtime Cache cannot
provide either alone.

### 2026-11-07: full eligible-catalog hourly pass (review candidate)

The seven-repository slice above is the deployed behavior until this change merges and
the runtime clone updates. The hourly scheduler's existing script-only, no-LLM wrapper
will run `jr/popularity_run.py` before the growth tick, under
the same thermal check, process lock and 600-second wrapper deadline. The popularity pass
gets a separate bounded GraphQL source-read budget and isolated worktree. Its
12-call/60-second source window starts after delivery reconciliation; a separate
210-second overall popularity runtime reserve may defer source work. It requests
at most 25 repositories per query through aliases bound to their canonical owner/name,
asks for `nameWithOwner`, numeric `databaseId`/`fullDatabaseId`, `stargazerCount` and
`forkCount`, and checks every response against the URL and any previously cited stable ID.
The opaque GraphQL node `id` is never used as the REST repository ID. The
[GitHub repository fields](https://docs.github.com/en/graphql/reference/repos#repository)
and [GraphQL rate rules](https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api)
are the provider contracts. Every canonical, non-quarantined repo is attempted once per
hour when the quota/time budget permits; no same-run retry, fabricated count or unsafe
fallback is allowed. The current production tree at `1a497be3` has 147 canonical distinct
URLs, six records with cited ID/date, and one known wrong-source Nyan URL, so 146 are
candidates pending each response's identity check. This is candidate coverage, not a
claim that all 146 source mappings have been independently validated.

A per-record receipt separates attempted/validated/deferred/excluded outcomes and age at
run start. GitHub GraphQL request count, observed point cost and remaining quota are
recorded separately; malformed or rate-limited responses stop later batches and set a
box-local cooldown. Failed/partial responses retain each record's last-good cited count.
The publisher stages only popularity files and that receipt, applies `scripts/validate.py`
and the existing review classifier, then opens or exact-head-updates a bot-owned
popularity-only PR. An existing head must match Jr's independently persisted
publication pin; Jr merges current main into that head and publishes only by
normal fast-forward push. The publisher verifies auto-merge is disarmed before
and after the update and refuses an uncertain remote state. A durable exact
commit intent precedes any push, delivery is saved before auto-merge arming,
and arming is tied to the bot commit with `--match-head-commit`. It never stages a growth recipe.
Branch protection, required checks and earned-trust auto-merge remain gates.
Every hourly run also reconciles pending popularity PRs through merge, deployed
API revision containing the merge, successful catalog cache invalidation and
sampled API plus exact rendered-count readback. Each transition and the fair
live-check sequence are persisted outside the repo for restart recovery. A
later live-verified snapshot that changes a sampled firmware supersedes an older
expectation only when commit ancestry proves the order; it does not certify
the older count. A fetched value is not visible merely because Jr wrote a PR.

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
