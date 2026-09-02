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

## Order of work (Felipe: "one after another, after spec")
1. **This spec.** ✓
2. **Audit + prune** existing sub-floor firmware (server-vampeta + the swept list).
3. **Build the floor** into the drain (TDD: sub-floor candidate skipped; above-either-floor
   authored; curated exempt).
