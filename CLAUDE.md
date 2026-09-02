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

## Web server fetches (`apps/web/lib/api-server.ts`)
Next.js Data Cache is **persistent and survives deploys** — a `fetch` cached with
`next: { revalidate }` can keep serving a deleted record (e.g. a removed firmware entry)
long after the live API returns 404. Server-side fetches in `api-server.ts` therefore use
`cache: "no-store"` so every server render reflects the current API response, never a
stale on-disk cache entry.

## Golden path for any change
SPEC before code · oracle/TDD first · cite-or-omit · verify the **real path** before
declaring done · land on main. Deterministic where it matters — no LLM in an answer path
that must be reproducible (board ranking, pin assignment, confidence gates).
