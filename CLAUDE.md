# CLAUDE.md — esp-atlas

## The motto — non-negotiable

> # 100% of esp-atlas info is verified and verifiable.

Every hard spec on this site is either **quoted** from an official source (the number
appears verbatim on a page you can open) or **derived** with the math shown and every
input cited. Nothing is asserted from a model's memory — ever. Two structural rules
enforce it:

- **Cite-or-omit.** A hard spec ships with a `sources[]` entry (`field` + live `url` +
  `verified` date) or it is **omitted**. Never guessed. (`price_tier` is the only
  editorial-exempt field.) `scripts/validate.py` + `check_sources_live.py` gate this in CI.
- **Derived ≠ quoted.** A computed value (e.g. `io.gpio_free`, `io.gpio_pins`) shows its
  derivation in `notes`, cites the pinout source AND the reserved-pins source, and is
  human-verifiable step by step. Verified against the source, not just plausible.

If you cannot verify a value against a real, current source, you do not have it. Omit it
and say so. A smaller true catalog beats a larger guessed one.

*(The `esp32-s31` lesson, in one line: a model claimed a real part didn't exist; the fix
was to make the official source the authority. That rule is now structural.)*

## How to work here
- **Contributor mechanics** (data model, schema, validate, one-pass record authoring): see `AGENTS.md`.
- **Ownership map / vocabulary** (which spec owns what): see `SPEC-INDEX.md` — it wins on any conflict.
- **Roadmap / current delivery**: see `BIBLE-PLAN.md`.
- **North star:** answer *"will THIS board do MY project, and exactly how do I wire it?"* — verifiably.

## Git & GitHub
- `git push` over SSH already authenticates as the repo owner — no account flip needed.
- Any `gh` call that **writes** (`pr create` · `pr close` · `pr merge` · tags · repo-settings
  API) must run as the personal account. Flip before, flip back after:
  `gh auth switch --user fcavalcantirj` … `gh auth switch --user <your default account>`.
  Leaving the wrong account active is the bug this rule exists to prevent — always restore it
  in the same turn, even if the command failed.
- Read-only calls need no flip: `GH_TOKEN=$(gh auth token --user fcavalcantirj) gh …`.
- **This repo is public.** Operational notes that name maintainer hosts, shell users, ssh keys
  or credential-file paths do not belong in it, even with no secret values in them. Keep them
  local and hand-carry them.
- Never run `git checkout <ref> -- .` to inspect another ref: it overwrites uncommitted work in
  the tree. Read with `git show <ref>:<path>` instead.

## Golden path for any change
SPEC before code · oracle/TDD first · cite-or-omit · verify the **real path** before
declaring done · land on main. Deterministic where it matters — no LLM in an answer path
that must be reproducible (board ranking, pin assignment, confidence gates).

## How the catalog grows itself (operations, 2026-11-09)

- **Hourly GitHub counts** (`.github/workflows/runtime-popularity.yml`) have **no `schedule:`**: GitHub's
  cron dropped most hourly slots (1 of 6 on 2026-11-07). An operator-run OS timer on the always-on runner
  dispatches the workflow at minute 07 UTC through `scripts/counts-dispatch.sh` (`workflow_dispatch`,
  `publish=true`, `source=host-timer`). Every run's name says who asked: `counts (host-timer)` is
  automation, `counts (manual-testing)` a hand test, and a hand-run is never evidence that automation
  works. Stop: disable the timer on the runner, or set the repo variable `POPULARITY_RUNTIME_ENABLED=0`.
  Details and the unit sketch: `DEPLOY.md` "Hourly GitHub counts"; reader in `apps/api/README.md`.
- **Demand → reviewed work → recorded outcome** (`SPEC-demand-work-consumer.md`, `SPEC-pam-discovery.md`).
  The daily demand runner makes one pass per **source class**, search demand (GSC/GA4) then PAM market
  leads, each with its own one-new-item-per-day slot (2026-11-08; a single shared slot had starved every
  PAM lead). A reservation is a receipt in `docs/demand/work-receipts.json` and a deterministic branch
  `jr/research-<key>`. The operator's coding delegate executes it from `docs/demand/EXECUTOR-PROMPT.md`;
  a relay step pushes the branch and opens the draft `jr-review` PR. After merge the runner verifies the
  deployed result itself: `catalog_search` (the exact public search of a bare SKU term) or
  `catalog_part` (each expected board id at `/api/parts/<id>`, the fuzzy search never closes a name hint).
  **`jr/work_record.py` is the only write path** into the queue/receipts pair for anyone but the broker
  (adopt, validate, link, attempt, settle, retry, check); it refuses any state the broker would defer on. Never
  edit those two JSON files by hand. A live receipt without a PR gets two UTC days of work; from the third it
  is exhausted (never resumed or launched, no longer holds its class) until a human settles or `retry`s it,
  and `work_record.py launch-state <key>` is the one launch rule for the operator's launcher.
- **Jr's tick never re-proposes what a tick PR already holds** (`jr/pending_prs.py`, §6 of
  `SPEC-jr-review-routing.md`): an OPEN tick PR holds every firmware it touches; a tick PR **closed
  unmerged is a 30-day veto of everything it proposed**. Disposing of duplicate tick PRs therefore means
  merge the one you keep first, then close the rest. A renamed upstream binds by GitHub's numeric repo id
  (both names must resolve to the same id); a slug mismatch alone never blocks.
- **Change discipline that worked.** Spec before code; RED test first and quote the RED count; every
  claim labelled `[TEST]` (offline) or `[REAL]` (observed on the live system); an independent reviewer
  reads the **exact head** and the merge is `gh pr merge --match-head-commit <sha>`; isolation in a
  worktree off `origin/main`, never in a shared checkout; two consecutive natural runs matched end to end
  (host receipt ↔ run id ↔ data commit ↔ live value) are the acceptance of an automation, nothing less.
  Coordination with the runner's operator happens in the project's Solvr room; claim a lane before
  editing, release it after.
- **Running the Python suites**: `PYTHONPATH=apps/core/src python3 -m pytest jr scripts -q` with Python
  **3.11 or newer** (older `fromisoformat` cannot read a trailing `Z`; macOS's 3.10 fails two tests on
  main for that reason alone). `jr/test_esp_image.py` and the sandbox tests need
  `pip install -r jr/requirements-image.txt` and a Linux host (`preexec_fn` limits). CI is 3.12.
