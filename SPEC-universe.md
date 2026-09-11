# SPEC — The Board Universe & the Honest Coverage Denominator

> esp-atlas catalogs ~90 boards today, but the gauge that drives allocation reports
> completion as *cataloged ÷ what-we-have* — it can never fall below what we already
> shipped, so it lies about how much of the real ESP32 board universe is missing. This
> spec builds the FOUNDATION for an honest denominator: a verified, committed
> **universe manifest** of every real ESP32-family board a tracked brand actually sells,
> and a **real coverage report** measured as *cataloged ÷ universe*. (Felipe, 2026-09-11.)

This slice does **not** author new boards and does **not** touch the live tick gauge or
allocator (`allocator.py` reads `boards_pct`; destabilizing it is a later, careful slice).
It ships the manifest, a read-only loader, and a report — nothing that runs in CI or tick.

## The universe inclusion boundary

The **universe** is: *every real, individually-documented ESP32-family board sold or
documented by a brand esp-atlas already tracks.*

- **Family scope.** ESP32 and its successors: `esp32`, `esp32-s2`, `esp32-s3`, `esp32-c3`,
  `esp32-c6`, `esp32-c5`, `esp32-h2`, `esp32-p4`, and any future Espressif-family MCU. The
  `mcu` field records which one. Non-ESP32 boards (RP2040, nRF, STM32, …) are out of scope
  even when sold by the same brand.
- **Brand scope.** Only brands esp-atlas already tracks under `data/boards/<brand>/`
  (adafruit, dfrobot, elecrow, espressif, freenove, heltec, lilygo, lolin, m5stack, seeed,
  …). Adding a brand to the universe is a deliberate, separate act — not implied here.
- **Cite-or-omit — no entry without a real source.** Every entry MUST carry a
  `source_url` that resolves live (HTTP 200) to a first-party or authoritative doc/product
  page for that exact board. If no live source can be verified, the board is **omitted** —
  an unsourced guess never enters the manifest. (Mirrors the repo-wide source-or-omit rule
  that `validate.py` enforces on `data/**`.)
- **Discontinued boards are in scope, marked.** A board that was really sold and documented
  belongs in the universe even after end-of-life; record it with `status: discontinued` so
  the denominator reflects the real historical universe, not just the current shelf. Use
  `status: active` for boards currently sold/documented.
- **Doc-page-sharing variants are distinct entries.** When a manufacturer ships a variant
  that shares a single doc page with its base board (e.g. *XIAO ESP32-S3 Sense* shares the
  *XIAO ESP32-S3* getting-started page), the variant is its own entry with its own
  `board_id`, pointing at the shared `source_url`, and carries a `note` explaining the
  shared page and what distinguishes the variant. This keeps the denominator honest: a
  variant a buyer can actually purchase is a real board to cover.

## The manifest format

The manifest lives at **`docs/universe/<brand>.yaml`** — one file per brand, committed to
the repo. It is a hand/offline-built ground-truth document, not generated at runtime.

Each file is a YAML mapping with a top-level `brand` key and a `boards` list. Each board
entry is a mapping:

```yaml
brand: seeed
boards:
  - board_id: xiao-esp32c3            # matches data/boards/<brand>/<board_id>/ when cataloged
    name: "Seeed Studio XIAO ESP32-C3"
    mcu: esp32-c3                      # the ESP32-family MCU
    source_url: "https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/"
    status: active                     # active | discontinued
    note: "optional free text"         # optional; required for shared-doc variants
```

Field rules:

- `board_id` — the catalog id for this board. It is the join key against
  `data/boards/<brand>/<board_id>/board.md` to DERIVE whether it is cataloged. It MUST be
  unique within the brand file.
- `name` — human-facing product name.
- `mcu` — the ESP32-family MCU id (e.g. `esp32-c3`, `esp32-s3`).
- `source_url` — a live, verified (HTTP 200) authoritative source. Required.
- `status` — `active` or `discontinued`. Required.
- `note` — optional free text; use it for variant explanations (shared doc page, what the
  variant adds) and discontinuation context.

**There is NO `in_catalog` flag.** Whether a board is cataloged is *derived* at load time
by checking for `data/boards/<brand>/<board_id>/board.md` (see below). Storing it would let
the manifest drift from the actual catalog; the filesystem is the single source of truth.

## How coverage is computed

Coverage is **cataloged ÷ universe** — the honest denominator.

- **cataloged** — DERIVED, never stored: a board_id counts as cataloged iff
  `data/boards/<brand>/<board_id>/board.md` exists on disk.
- **universe** — the count of entries in the manifest for that brand.
- **per-brand** — `{universe_count, cataloged_count, missing: [board_ids]}` where `missing`
  is every manifest `board_id` with no `board.md`.
- **overall** — the sum of per-brand universe and cataloged counts, and overall
  `cataloged / universe` percentage.

Example (seeed, this slice): universe = 5 (`xiao-esp32c3`, `xiao-esp32c6`, `xiao-esp32s3`,
`xiao-esp32c5`, `xiao-esp32s3-sense`); cataloged = 3 (c3, c6, s3 exist under
`data/boards/seeed/`); missing = `[xiao-esp32c5, xiao-esp32s3-sense]` → **3/5 = 60%**.

## Build-and-commit, never fetched at runtime

The manifest is **built OFFLINE and committed**, exactly like `docs/demand/`:

- URL verification (the HTTP-200 cite-or-omit check) happens when a human/agent *authors*
  the manifest, offline. The committed `.yaml` is the frozen result.
- **`jr/universe.py` never touches the network** and never writes to `data/`. It only reads
  the committed manifests and the `data/boards/` filesystem.
- Nothing in `tick.py`, `allocator.py`, CI, or `validate.py` fetches or depends on the
  manifest. The manifest lives under `docs/` (not `data/**/*.md`), so `validate.py` — which
  validates `data/**` frontmatter — does not see it and stays green.

## Deliverables

1. `SPEC-universe.md` — this file.
2. `docs/universe/<brand>.yaml` — the committed manifest (seeded: `seeed.yaml`).
3. `jr/universe.py` — `load_universe(docs_dir)` and `coverage(universe, boards_root)`,
   read-only, no network, no writes to `data/`.
4. `docs/universe/coverage.md` — a committed sample of the rendered real gauge, plus a
   `render_coverage_md()` function that produces it.

## Out of scope (later slices)

- Authoring the missing boards (`xiao-esp32c5`, `xiao-esp32s3-sense`, …).
- Wiring the honest denominator into the live `boards_pct` / tick gauge / allocator.
- Expanding the universe beyond the `seeed` seed to every tracked brand.
