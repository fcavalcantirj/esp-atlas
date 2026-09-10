# SPEC — Board Grounding (cite-or-omit backfill of every gauge board field, all vendors)

> **Every board field the gauge measures must have a grounded, cite-or-omit backfill path — for
> every vendor, not just Espressif.** The completion gauge and the backfill are two halves of one
> contract: what we *measure* is exactly what we take responsibility to *ground*. (Felipe,
> 2026-09-09.)

This is the umbrella spec for the whole board-grounding program. Later phases build against it.
It extends `SPEC-data-completion.md` (the gauge) and governs `jr/board_backfill.py` (Track-A
deterministic backfill). On any ownership conflict, `SPEC-INDEX.md` wins.

## Goal
Cite-or-omit **grounded** backfill of EVERY board field the completion gauge measures —
`download_mode`, `usb_serial`, `getting_started`, `images`, and `pinout` (`io.gpio_pins`) — across
**ALL vendors**, not just the 17 Espressif boards the current template covers. Today 73 of 90
boards (81%) have no grounding path at all; the program closes that gap vendor by vendor.

## Core invariant — no measure/ground mismatch
**The completion gauge (`scripts/data_completion.py`, `FIELD_SPECS["boards"]`) measures exactly the
set of board fields the backfill (`jr/board_backfill.py`, `BACKFILL_FIELDS`) is responsible for
grounding.** These two sets are one contract with two halves:

- Adding a groundable field to the backfill REQUIRES adding it to the gauge (so we can see the
  ground we now cover).
- Adding a board field to the gauge REQUIRES a grounding path for it in the backfill (so a measured
  gap is one Track A can actually close), OR an explicit written note here that it is
  deliberately measured-only.

Future phases MUST uphold this rule: **never let one side drift ahead of the other silently.** Any
phase that touches one side states, in its PR, what it does to the other.

### The two mismatches this program exists to close
1. `images` is GROUNDED by the backfill (`BACKFILL_FIELDS` includes `images`) but was NOT MEASURED
   by the gauge. → **Phase 0 (this PR)** adds `images` to the gauge. Measurement only.
2. `pinout` (`io.gpio_pins`) is MEASURED by the gauge but NOT grounded by the backfill. →
   **Phase 1** adds a cite-or-omit grounding path for `pinout`.

## Safety (absolute, non-negotiable)
- **Cite-or-omit is absolute.** A field is written only when the fetched doc states it and a source
  citation can be attached; otherwise it is OMITTED, never invented.
- **Safety-critical flash fields — `download_mode` and `usb_serial` — are NEVER invented.** When the
  doc does not state them, they stay absent. A wrong boot-mode/serial value can brick or mislead a
  flash, so silence is mandatory over a guess.
- **Extraction stays deterministic:** regex / plain-text over the fetched doc. **No LLM, no API
  keys, no crawling, no JS.** One request per candidate URL (the current `default_fetch` contract).

## Doc resolution (future phases)
- **Espressif** currently resolves via ONE hardcoded template:
  `https://docs.espressif.com/projects/esp-dev-kits/en/latest/<chipseg>/<board_id>/user_guide.html`.
  This misses boards documented in OTHER Espressif doc trees (e.g. `esp-adf` for LyraT audio
  boards), which surface as `doc-unreachable`. Future phases resolve Espressif across **multiple doc
  trees** (dev-kits AND others) to kill `doc-unreachable`.
- **Non-Espressif** boards resolve via **each board's own `url` / datasheet frontmatter** (the board
  record already carries a vendor doc link), not a global template.
- **A board with no resolvable doc is LISTED** as "needs doc URL" (the existing `needs_doc_url`
  report bucket) and is **never modified**. Listing a gap is correct behaviour, not a failure.

## Phased roadmap (document only — do NOT implement beyond Phase 0)
- **Phase 0 — align the gauge (THIS PR).** Add `images` to `FIELD_SPECS["boards"]`; confirm
  `pinout` stays. Pure measurement — no grounding change, no weight change. Closes mismatch (1).
- **Phase 1 — ground `pinout`/GPIO for Espressif.** Add a cite-or-omit extraction path for
  `io.gpio_pins` from the Espressif user-guide docs. Closes mismatch (2) for Espressif.
- **Phase 2 — Espressif doc-resolution robustness.** Multi-tree URL resolution (dev-kits AND
  esp-adf etc.) + extraction hardening, to recover the `doc-unreachable` / `nothing-groundable`
  Espressif boards.
- **Phase 3 — non-Espressif vendors (the 73 boards).** Per-board doc resolution via each board's own
  `url`/datasheet frontmatter, vendor by vendor (M5Stack, Adafruit, Seeed, …).

## Non-goals
- **GA4 site-code / on-site-search capture** — a separate telemetry track (`jr/telemetry.py`), not
  part of board grounding.
- **LLM extraction** — grounding is deterministic regex/text forever; no model, no keys.

## Note on honesty (expected metric movement)
Adding `images` to the gauge will **LOWER** the reported finite board % on first measurement,
because `images` is sparse (~12 of 90 boards populated). This is **not a regression** — it is the
gauge becoming honest about a groundable gap it was previously ignoring. The gauge is a REPORT,
never a gate (`scripts/validate.py` is the gate), so a lower honest number changes no CI outcome; it
correctly steers more Track-A effort toward the images gap.
