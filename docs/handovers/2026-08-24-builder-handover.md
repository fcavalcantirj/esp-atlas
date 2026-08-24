# Builder handover — esp-atlas home-explorer / wizard build

You are the **executor/builder** for esp-atlas. The **architect** is the agent
`dasbrow_brains`, reachable in the Solvr room below. You build; the architect
designs and reviews. **Align in the room before and during the build.**

---

## Step 1 — Hydrate on the repository
Repo: `github.com/fcavalcantirj/esp-atlas` (you have it checked out locally under
`~/code/esp-atlas`, or clone it). Read, in this order:
1. **`SPEC-INDEX.md`** — the authority. On ANY conflict between specs, it wins.
   It has the ownership map, the canonical glossary, the collision resolutions
   (C1–C6), the architecture ruling (§4), and the open gaps (G1–G7).
2. `SPEC.md` (governance, entity model, CI gate) and `INTERFACE-SPEC.md` (API/site/CLI/Groq).
3. `SPEC-home-explorer.md` (what you're building), plus `SPEC-hosting-lane.md`,
   `SPEC-wizard.md`, `SPEC-freshness.md`, `SPEC-data-population.md`, `SPEC-discovery.md`.
4. Codebase: `apps/core` (search/wizard/index/facets), `apps/api` (FastAPI),
   `apps/cli`, `apps/web` (Next.js), `data/` (records), `schema/`, `scripts/`
   (`validate.py`, `build_index.py`, `check_sources_live.py`, `wizard_dead_ends.py`).

## Step 2 — Hydrate on the Solvr room
- Load the `solvr` skill (or `curl -sL https://solvr.dev/install.sh | bash`).
- Room: **`esp-atlas-build`** → https://solvr.dev/rooms/esp-atlas-build (public: readable by anyone).
- To **write/report**, you need the room's write-token — **ask Felipe for it**
  (it is deliberately NOT committed here; never commit Solvr tokens to this public repo).
  Join: `solvr room-join esp-atlas-build --token <token-from-Felipe>`.
  (If you are an agent claimed by the same human as the architect, you can instead
  `solvr my-rooms` → `solvr handshake esp-atlas-build` with no token.)
- Read the architect's messages (`solvr room esp-atlas-build`).

## Step 3 — Confirm & align BEFORE writing code
Post in the room: (a) confirm you've read `SPEC-INDEX.md`, (b) which layer you're
starting, (c) your concrete plan. **Wait for the architect's ack before coding.**

## Step 4 — Build (one layer at a time)
Start at **L1** (`SPEC-home-explorer.md` §8):
- **L1** — replace the static `PRESETS` array with generated examples from our data;
  simplify the classic (Board) Wizard to plain-language questions; demote specifics
  (form/mesh/USB/**raw memory MB**) to **Advanced**. Keep the "Runs a web server"
  **intent toggle top-level** (SPEC-INDEX C4). Extend the dead-ends oracle so every
  generated example resolves to ≥1 result.
- **L2** — the firmware/flash matrix + flash-right-here bridge (SPEC-wizard rails).
- **L3** — live signal (discovery adapter pack) + click-analytics ranking.

**Do NOT build yet** (gaps — need schema/spec first, per SPEC-INDEX §5):
`prompt-recipe` and `example` entities (G1/G2), firmware `tags` (G5). Raise these
in the room; the architect will spec them before you implement.

## Step 5 — Rules (non-negotiable)
- **PR-only.** `main` is branch-protected; open a branch → PR. CI (`schema` +
  `tests`/oracle + `sources-live`) must be **green**. **Humans merge**, not you.
- **Cite-or-omit.** Every hard spec carries a live `sources:` entry; never guess a value.
- **Conventional commits.** Match the repo's style.
- **Report continuously in the room.** Blocked or a spec seems wrong? **Ask — don't guess.**
- **Verify, don't claim.** Run the validators + exercise the feature; report real numbers.

## Open decision (pending Felipe — do not assume)
Global click-analytics ranking needs a runtime store, which conflicts with SPEC.md's
"no database / static." Blocks L3 only, not L1/L2. See `SPEC-INDEX.md` §4.
