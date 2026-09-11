# SPEC — Non-Espressif board backfill (per-vendor First-Flash fields)

> **The finite ground is Espressif-shaped.** `jr/board_backfill.py` fills the First-Flash /
> physical board fields (`download_mode`, `usb_serial`, `getting_started`, `images`) — but only
> for `data/boards/espressif/*`, because its extractors key off the structured
> `docs.espressif.com/projects/esp-dev-kits` user guides. The other **73 of 90 boards** (m5stack,
> adafruit, lilygo, lolin, dfrobot, sparkfun, heltec, …) have **zero** of these fields. That is the
> entire reason the trend shows `getting_started`/`images`/`pinout`/`download_mode` stuck at
> ~17–19% (= the Espressif fraction). Empirically verified on `origin/main` @ 344befb, 2026-09-10.
> (Extends SPEC-data-completion.md and the board_backfill v1 scope; 2026-09-10.)

## What this is (and is not)
- **Deterministic, cite-or-omit backfill — never LLM synthesis.** Same contract as v1
  `board_backfill.py`: a field is written ONLY when extracted from a fetched, cited vendor page.
  Absence stays neutral; nothing is invented. This spec does **not** relax cite-or-omit.
- It **extends** `board_backfill.py`'s reach to non-Espressif vendors. It does **not** change the
  Espressif path, the field set, or the tick's allocator split.
- It is delivered **one vendor at a time** (divide & conquer). Each vendor is an independent slice
  with its own PR, its own tests, and a measurable coverage jump — never a big-bang batch.

## Root cause recap (measured)
`board_backfill.run()` iterates `boards_dir/"espressif"` only; every other brand dir is appended to
`needs_doc_url` and never touched. Espressif boards are ~complete (15–17/17 across the four fields);
all 73 non-Espressif boards are at 0. `io.gpio_pins` (the trend's `pinout`) is a special case — it
is NOT in `BACKFILL_FIELDS` even for Espressif (it arrives via new-board authoring), so it needs its
own treatment (§ Pinout, below), separate from the vendor rollout.

## The generalization: a per-vendor doc-URL resolver
v1 hardcodes one base (`USER_GUIDE_BASE = docs.espressif.com/...`). v2 introduces a **resolver
registry**: `VENDOR_DOC_RESOLVERS: dict[brand -> Callable[[board_id, frontmatter] -> list[url]]]`.

- Each resolver returns the **candidate official doc/product URLs** for a board on that vendor's own
  domain (ordered best-first). Espressif's existing logic becomes the `"espressif"` resolver —
  behaviour-preserving refactor, no output change.
- The **field extractors are reused unchanged** where they generalize (`extract_download_mode`,
  `extract_usb_serial`, `extract_getting_started`, `extract_images`). They operate on fetched raw
  text/HTML with vendor-neutral heuristics (sentence scan, `_BRIDGE_TOKENS`, `_IMG_SRC`); a field
  that the heuristic can't ground on a given vendor's page is simply omitted (cite-or-omit).
- `run()` iterates **every** brand dir that has a registered resolver (not just `espressif`); brands
  with no resolver yet fall through to `needs_doc_url` exactly as today (no regression, visible TODO).

This keeps the risky, vendor-specific part (URL shape + page structure) isolated to a small resolver
function per vendor, while the extraction/citation core stays single-sourced and tested once.

## Slice order (one PR each; stop-and-verify between)
1. **Refactor to the resolver registry** — extract Espressif into a resolver, prove byte-identical
   output on the 17 Espressif boards (golden test), no coverage change. Pure structural PR.
2. **m5stack (13 boards)** — first non-Espressif vendor. Chosen first: largest non-Espressif brand,
   structured docs at `docs.m5stack.com`, and it is the operator's own hardware ecosystem (highest
   verifiability — the extracted facts can be checked against physical boards). Target fields:
   `download_mode`, `usb_serial`, `getting_started`, `images`. The exact `docs.m5stack.com` URL
   pattern is confirmed by a live fetch during the build, not guessed.
3. **Subsequent vendors** — adafruit (11), lilygo (10), then the long tail — each its own slice,
   ordered by board count × doc-structure regularity. Re-evaluate after each: a vendor whose docs
   are not machine-extractable is flagged and **skipped explicitly** (logged, never silently), not
   forced.
5. **heltec (5 boards)** — `heltec_doc_candidates` on `docs.heltec.org`. UNLIKE the
   m5stack/adafruit/lilygo per-board maps, heltec's doc URL is a clean **deterministic rule**
   (verified live 2026-09-11 to yield all 5 real doc pages, 200, each describing the correct
   V3/ESP32-S3 board): strip the `heltec-` prefix, strip a trailing `-v3`, replace `-`→`_`, then
   `https://docs.heltec.org/en/node/esp32/<that>/index.html`. All 5 ids fit the rule exactly, so
   none is hardcoded (a future non-fitting board would go in a small verified override map, never
   forced onto the rule); the resolver only claims `heltec-`-prefixed ids (else `[]` → skipped
   doc-unreachable, never a guessed URL). **Grounds:** `getting_started` for all 5 (the resolved
   200 doc page IS the link); `usb_serial` only where the page NAMES the bridge — wifi-kit-32-v3
   and wifi-lora-32-v3 state "Integrated CP2102 … serial port chip" → `cp2102` (in the real data
   these are already filled, so a real run adds only `getting_started`). **Omitted:** `usb_serial`
   on wireless-stick-v3 / wireless-tracker / wireless-paper (their doc pages name no bridge — the
   only "Bridge"/"Boot" tokens are site-nav chrome, which must NOT false-positive the extractor);
   `download_mode` on all 5 (no Boot+Reset "Firmware Download mode" sentence); `images` on all 5
   (no og:image, and no dedicated heltec image extractor this slice). Honest per-board delta on a
   real run: 0→1 (`getting_started`), with `download_mode` + `images` explicitly omitted.

## Pinout (`io.gpio_pins`) — deferred, separate track
The trend's `pinout` is the `io.gpio_pins` **array** (raw exposed GPIO numbers), the hardest field:
it needs a machine-readable pin table, not prose or a URL. It is out of scope for the vendor
rollout above and gets its own spec after ≥1 vendor slice lands, because its extraction problem is
orthogonal to doc-URL resolution. (Note: `images.pinout` — the diagram *URL* — is easy and rides
`extract_images` in the vendor slices; do not conflate it with `io.gpio_pins`.)

## Guarantees / non-negotiables
- **REPORT-driven, deterministic.** No clock in core; same board + same fetched page ⇒ same output.
- **Cite-or-omit preserved.** Every written field carries its source; unfetchable ⇒ omitted, board
  left unchanged (never a partial/invented write).
- **No Espressif regression.** Slice 1 is guarded by a golden test over the 17 Espressif boards.
- **Network at the edges only.** Fetching stays behind the same injection seam v1 uses, so the
  extraction/resolver logic is unit-tested offline with fixture pages (realistic vendor HTML, never
  synthetic lorem).
- **File ceiling.** If `board_backfill.py` approaches ~900 lines, split resolvers into
  `jr/board_resolvers.py`; keep extraction and orchestration separable.

## Success signal (how we know it worked)
After the m5stack slice, `data-trend.jsonl` (v2 `entity_fields`) shows `boards.getting_started`,
`boards.images`, `boards.download_mode`, `boards.usb_serial` counts rise by the number of m5stack
boards whose docs yielded each field — and the per-field **momentum** verdict flips from `flat` to
`improving`. That is the measurement loop (SPEC-data-trend v2) closing on a real fix.
