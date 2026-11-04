# SPEC — Jr refactor: gate-at-ingest

> **Status:** planned, not built. Jr crons (`jr-drain`, `jr-review-merge`) are **PAUSED** as of
> 2026-09-02 pending this refactor. Live catalog is stable and untouched.

## Problem — why we're doing this

The Jr pipeline is **generate-then-clean**, and that is the flaw. The drain scrapes broadly and
**admits junk** — GitHub forks instead of the popular original, sub-floor repos, duplicates,
repo-status banner titles (`【Maintenance completed】…`). A whole **downstream apparatus** then exists
to mop it up: the `jr-review-merge` cron (category fixes + dup collapse + auto-merge), `validate.py`
in CI, and manual/agent firefighting.

It is always cheaper to **not ingest junk** than to ingest it and maintain machinery to clean it.
Evidence from a single day (2026-09-02): a 4★ fork cataloged instead of its 48★ original; an
AI-StackChan duplicate; a banner title; and — because the delegate and the drain **share one working
tree** — two **destructive collision PRs** (#100/#101) that would have deleted ~1,700 lines.

## Principle

**Quality is enforced at ADMISSION**, before a candidate becomes a PR or commit. Nothing enters the
catalog that is not already: fork-resolved, above floor, deduped, clean-titled. **The catalog is
clean by construction**, and the downstream cleanup layer is deleted.

## The ingest gate — ordered admission checks

For each scraped candidate, run in order; reject or transform *before* authoring. All four already
exist as verified logic (118 passing tests on the logic branch — see "Reuses" below):

1. **Fork → source (GUARDED — do NOT blindly jump to the GitHub parent).** If a candidate is a
   fork, consider its network root (`.source`). **Resolve ONLY when both hold: (a) source stars >
   fork stars, AND (b) it's the same project/platform** (not a divergent hard-fork, not a
   cross-platform parent). Otherwise **keep the fork** — it's either the more-popular entry or a
   meaningful platform-specific port. Evidence the guard is required (2026-09-02 sweep, 7 forks):
   ✅ resolve flipper→Sor3nt (425★), zx-spectrum→…-external (48★), sshclient→fernandofatech (67★);
   ⛔ keep anarch-cardputer (14★ > its 12★ ESPboy parent) and cardputer-mp3-adv (16★ > 7★ parent);
   ⛔ never resolve circuitpython→micropython (distinct project) or
   claude-desktop-buddy-cardputer→anthropics/claude-desktop-buddy (non-Cardputer parent).
   *(jr/forks.py — add this guard; the current resolver walks to root without it.)*
2. **Popularity floor.** Keep iff the resolved source has **stars ≥ 25 OR forks ≥ 25**. Downloads are
   **not** a metric anywhere. *(jr/scorer.py)*
3. **Dedup.** If the resolved source is already represented (by repo identity / id), skip.
4. **Title sanitize.** Strip status banners (`【…】`, WIP, DEPRECATED, `[test]`, …) from the name.
   *(jr/normalize.py — already shipped to main)*

5. **Device-build evidence** *(added 2026-11-04, review finding 3; tightened 2026-11-04 on the
   owner's rule)*. The repo is admitted only with evidence that it **targets an ESP chip** — never
   a generic build file or binary; an ambiguous repo goes to a human, never guessed. ESP target:
   - `platformio`: a `platformio.ini` whose `platform` names `espressif32` (extra_configs and
     `${section.option}` resolved);
   - `idf_project`: a `CMakeLists.txt` including ESP-IDF's `project.cmake` **and** an ESP target
     stated — `CONFIG_IDF_TARGET` in `sdkconfig.defaults` (or a committed `sdkconfig`), `targets`
     in an `idf_component.yml`, or `target` in a `dependencies.lock` (`linux` is not an ESP);
   - `arduino_sketch`: a `*.ino` **and** an ESP board named — a `sketch.yaml` fqbn
     `<vendor>:esp32:<board>`, a `.github/workflows` file compiling for one, or
     `library.properties` `architectures` listing `esp32` (sketches and board files under vendored
     trees — `lib/`, `libraries/`, `components/`, `managed_components/`, `vendor/`, … — are other
     projects' and never count);
   - `release_bin`: a non-draft release `.bin` (ONE GET through `jr/safe_fetch.py`) that `jr/esp_image.py`
     validates OFFLINE as a whole ESP image (owner spec 2026-11-04): parsed with esptool's image
     module pinned exactly (`esptool==5.6.0`, `jr/requirements-image.txt`; never its serial or
     flashing code), a chip id the parser knows, EVERY declared segment walked (padding segments
     at load address 0 and zero-length segments are legal), the checksum byte and — when the
     header's `hash_appended` is set — the appended SHA-256 recomputed and compared. A clean parse
     or esptool's `verify()` alone never counts. Unknown chip, a merged flash image (no header at
     offset 0, e.g. the bootloader at 0x1000, or bootloader + partition table at 0x8000 + app),
     truncation, a checksum/digest mismatch, unexplained non-0xFF bytes after the image, or any
     parser exception → `needs_review` with the validator's reasons. Passing means chip target +
     integrity only, never authorship or board compatibility.
     **The fetch** (`jr/safe_fetch.py`, owner spec 2026-11-04): https only on port 443, no URL
     credentials; redirects followed by hand, at most 5, every hop re-validated; each hop's host
     resolved once and refused if ANY answer is private, loopback, link-local, multicast, reserved,
     unspecified, shared (100.64/10), an IPv4-mapped form of those, or a 6to4/NAT64/Teredo address;
     the connection is dialed to that validated address (TLS verifies the hostname), so DNS
     rebinding cannot swap it. The 16 MB cap counts bytes received while streaming —
     Content-Length is never trusted (absent, wrong or lying), a closing server is read to the
     close — and one byte over aborts. Connect (10 s), read (30 s) and total (120 s, a watchdog
     that also bounds slow-dripped headers and DNS) timeouts.
     **The parse** (`jr/image_sandbox.py`, owner spec 2026-11-04): `esp_image.validate` runs in a
     fresh `sys.executable -I -B` child under bubblewrap (`/usr/bin/bwrap`): new net, pid, ipc,
     uts, user and cgroup namespaces, `--disable-userns`, `--cap-drop ALL`, `--new-session`,
     `--die-with-parent`, `--clearenv`; a read-only tmpfs root holding only read-only binds of the
     interpreter's prefixes, esptool's site-packages, the validator module, the loader's
     libraries (`/usr/lib`, `/lib*`, `ld.so.cache`), `/dev/null` + `/dev/urandom` and a one-line
     `/etc/passwd` of its own — no `/home`, `/proc`, `/tmp`, serial device or host config, and
     every other directory on the way is 0111 (not listable). Hard RLIMIT_AS 512 MB, RLIMIT_CPU
     30 s, RLIMIT_NOFILE 64, RLIMIT_FSIZE 0, RLIMIT_CORE 0 set before exec; RLIMIT_NPROC 0 set
     as the child's first act (before exec it would make the kernel refuse the user namespace);
     a 60 s wall-clock kill in the parent. The asset arrives on stdin only. On top, a Python
     guard: `socket` patched before esptool is imported and a PEP 578 audit hook refusing
     socket, ctypes and process-start events, writes, reads/listings outside the bound roots,
     device-node opens, file mutation, signals and rlimit changes.
     **Fail closed:** no bwrap, or bwrap refusing to build the sandbox (namespaces denied), is
     `needs_review` with reason `sandbox_unavailable` — there is no unsandboxed fallback.
     **Mapping:** a refused, timed-out or over-cap fetch, a 404, an unavailable sandbox, and a
     validator child that crashed, was killed, timed out or printed anything but a well-formed
     result →
     `needs_review` (never `esp_target`); a 5xx/429, DNS failure or refused connection is an
     outage → unknown (`device_evidence_unreadable`, retried).

   Three verdicts. **`esp_target`** → the admit path continues. **`needs_review`** — only the
   ambiguous half was found (project.cmake with no stated target, a bare `.ino`, a `.bin` the
   validator sends to review, a `.uf2`/`.bin.gz` only, an `idf_component.yml` with no project) → not admitted,
   recorded rejected `needs_review_target` with the reject TTL (`memory.NO_BUILD_SIGNAL_DAYS`, so
   it is not re-checked hourly) and listed in the tick PR body under "Needs owner review" with the
   citing URL and why. **`not_device_firmware`** — no signal at all → rejected, remembered
   `memory.NO_BUILD_SIGNAL_DAYS`. An endpoint that failed for a reason other than 404 is unknown,
   never a verdict: `device_evidence_unreadable`, retried after `memory.UNRESOLVED_REJECT_DAYS`.
   Runs last (it costs 1–15 reads), on every path that authors a record: launcher + submissions
   (jr/stage_admit.py) and the topics/launcher drain (jr/drain.score_candidates). Topics and
   descriptions naming a board are NOT evidence: a Go server (rebelthor/warble) passed checks 1–4
   on its `esp32-s3`/`m5stack` topics alone.
   *(jr/device_evidence.py; read-only catalog audit printing the three classes:
   scripts/device_evidence_audit.py)*

Only candidates passing all five are authored.

## What gets DELETED

- **`jr-review-merge` cron** — its entire job (category fixes, dup collapse, guard check, auto-merge,
  the 🚀/⏸️/✅ status message) exists only to clean leaked junk. With gate-at-ingest there is nothing
  to fix → **remove the cron** and the emoji-status problem disappears with it.
- **The manual-merge / firefight flow.**
- **Kept:** `validate.py` (now also enforces the floor as a mechanical backstop), `jr-telemetry`.

## Drain output model — DECIDED: pull request + auto-merge on green

**Superseded 2026-09-03.** An earlier revision of this spec decided *direct-to-main*. Felipe
rejected that: it puts the Vercel deploy in front of any CI, and it makes
[`how-we-work`](apps/web/app/how-we-work/page.tsx)'s "it never writes to main" untrue.

The tick **opens a pull request** and then calls `gh pr merge --auto --squash`. CI decides; a human
may veto. *Bot proposes, CI disposes.* One squashed commit per tick, so a bad tick is a one-line
revert.

**Branch protection is not a nicety here — it IS the gate.** Verified on 2026-09-04: with no
protection configured, `gh pr merge --auto` does not queue, it merges **immediately**, because
auto-merge has no required checks to wait on. An unprotected repo therefore turns this model back
into direct-to-main under another name. `main` must require `schema`, `tests` and `jr-tests` before
the tick goes live, and the tick's preflight must fail red when protection is missing or its
required-check list is empty — not merely when auto-merge is switched off.

The publisher still self-validates before it pushes (`validate.py` once per tick, then the test
suite only if something was written), but that is now defence in depth rather than the only gate.

## One-time migration of the existing catalog

Run the tested `catalog_migrate` once: **strip downloads → resolve existing forks to originals →
purge still-sub-floor → `validate` green**. (e.g. zx-spectrum `internal` 4★ → `external` 48★; ~38
entries evaluated against the new floor.) Produce a diff for review **before** merge.

## Reuses existing verified work (not wasted)

The logic branch already holds, with **118 passing tests**:
`jr/forks.py` (resolver) · `jr/scorer.py` (floor) · `jr/catalog_migrate.py` + `scripts/strip_downloads.py`
(migration) · `jr/normalize.py` (sanitizer, already on main). The refactor **wires these into drain
admission and deletes the review cron** — it does not rebuild them.

## Build steps (small + sequenced — crons paused, so no collision, no timeouts)

1. **Land the logic** — rebase the logic branch on `main`; floor + fork-resolver + migration
   functions + `validate.py` floor-check. (Verify tests; the guard's "unparsable" glitch has
   false-FAILed clean runs — verify by running the suite directly.)
2. **Run the one-time migration** → diff → review → merge.
3. **Wire the 4 gates into drain admission**; **delete `jr-review-merge`**; set the tick's output
   to **pull request + `gh pr merge --auto --squash`** behind branch protection, keeping
   self-validate-before-push (`validate.py` green before the branch is pushed) as defence in depth.
4. **Verify** with a dry-run drain: a fork / sub-floor / dup / banner-title candidate is rejected or
   transformed at admission, and a red `validate.py` aborts the push.

## Acceptance

- Given a fork, sub-floor repo, duplicate, or banner-title candidate, the drain **rejects or
  transforms it at admission** (covered by tests).
- **No `jr-review-merge` cron.** `validate.py` enforces the floor.
- Catalog invariant: **0 forks** (all resolved to originals), **0 sub-floor**, **0 dups**, **0 banner
  titles** — and it stays that way without downstream cleanup.

## If it still needs babysitting → change / improve / recreate Jr

After step 4, judge by upkeep. If gate-at-ingest is genuinely low-maintenance, keep it. If it still
needs babysitting, **we iterate — change, improve, or recreate Jr** (not abandon it). Jr stays a
living system; the bar is that it earns its keep without firefighting.
