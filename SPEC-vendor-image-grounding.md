# SPEC — Per-vendor board image grounding (photo + pinout diagram)

> **Images live on each vendor's own site — but you can't find them by filename.** The board
> `images.photo` (visual identification) and `images.pinout` (the diagram a maker wires from) are
> hosted on each vendor's product/doc page. `board_backfill.extract_images` finds them by FILENAME
> pattern (`pinout`, `annotated-photo`, `isometric`, `layout-front`, …) — which matches
> `docs.espressif.com` naming and NOTHING else. Every non-Espressif vendor serves images from a CDN
> with opaque names (e.g. m5stack → `…/K150-stickS3_main-products_01.webp` on Aliyun OSS), so
> `images` is stuck at 17/90 (all Espressif). This spec grounds images **per vendor, by HTML
> context**, one vendor at a time. Verified against real fixtures on `origin/main`, 2026-09-11.
> (Extends SPEC-board-backfill-vendors.md; sibling to the doc-URL resolver registry.)

## Safety first — this field is flash-/wiring-critical
A wrong `images.pinout` is worse than a missing one: a maker wires from it and can fry a board.
So the bar is **high-confidence-or-omit**, stricter than ordinary cite-or-omit:
- An image is grounded as `pinout` ONLY when the page gives an explicit, vendor-specific signal that
  it IS the pinout diagram (a "Pinout"/"PinMap"/"Pin Map" section heading it sits under, or alt/title
  text saying pinout). A merely plausible product image is NEVER promoted to `pinout`.
- An image is grounded as `photo` ONLY when it is clearly the board's identifying product shot
  (vendor-specific signal: the hero/main-product image slot, or alt text naming the board). When in
  doubt, omit. A photo mis-pick is low-harm but still cite-or-omit.
- If a vendor's page yields neither with confidence, `images` stays omitted for that board. That is
  an acceptable, honest outcome — never guess.

## Architecture: a per-vendor image-extractor registry
Mirror the doc-URL resolver registry. Add:

`IMAGE_EXTRACTORS: dict[str, Callable[[raw_html, doc_url] -> dict | None]]`

- Keyed by brand. Each extractor returns `{"photo": url?, "pinout": url?}` (absolute URLs) or `None`.
- The **Espressif entry is the current `extract_images`**, unchanged — behaviour-preserving (its
  filename heuristic keeps working for `docs.espressif.com`).
- `_extract_for`/`backfill_board` calls `IMAGE_EXTRACTORS.get(brand, <espressif default>)` for the
  `images` field instead of the hardcoded `extract_images`. A brand with no image extractor yet
  falls back to the Espressif filename heuristic (which simply finds nothing on their CDN → omit, no
  regression, no bad data).
- Each vendor extractor encodes that vendor's page structure (how it marks a pinout section / hero
  image), derived from the REAL fixtures already committed under `jr/fixtures/board_backfill/`.

## Slice order (one vendor per PR; verify between — VERY slowly)
Same discipline as the resolver rollout. Each slice: study the real fixture(s), write the
vendor-specific context rule, TDD, prove on the fixture which boards ground a photo and/or pinout,
land through CI, watch the `images` count move, THEN next vendor.
1. **m5stack** — first (operator's ecosystem; fixtures already present). Determine from the real
   `m5stick-s3`/`m5cardputer`/`m5stack-core2` fixtures how m5stack marks the pinout diagram (section
   heading / anchor near the image) and the main product photo. Ground only what's unambiguous.
2. **adafruit** — its pinout diagrams live on a separate `/pinouts` guide page (noted in Slice 3);
   the extractor may need to follow that sub-page. Photo from the Learn hero.
3. **lilygo** — from its fixtures.
4. Tail vendors as they get doc resolvers.

## Non-goals (explicit)
- **`io.gpio_pins` (the numeric GPIO array — the trend's `pinout` field) is NOT this spec.** That
  needs a machine-readable pin *table*, a different extraction problem; its own later spec. This spec
  moves `images.photo` + `images.pinout` (the diagram *URL*), which is the `images` completion field.
- No LLM vision/classification. Grounding is deterministic HTML-context rules only — auditable,
  cite-or-omit, testable offline against the committed fixtures.
- No change to the doc-URL resolvers, stage_backfill, or the allocator.

## Guarantees
- **Deterministic & offline-testable.** Extractors take `(raw_html, doc_url)`; tested against the
  committed real fixtures. No network in tests.
- **No Espressif regression** — its extractor is the unchanged default; a golden test pins it.
- **High-confidence-or-omit** for `pinout` (safety), cite-or-omit for `photo`. Every grounded image
  is an absolute URL on the vendor's domain/CDN, carried with its `{field, url, verified}` source.
- **File ceiling** — if `board_backfill.py` nears ~900 lines, split image extractors into
  `jr/board_image_extractors.py`.

## Success signal
After the m5stack slice, the v2 trend's `boards.images` count rises by the number of m5stack boards
whose page yielded a confident photo and/or pinout diagram, and its momentum flips `flat → improving`
— the first movement on `images` since the series began. Measured, cited, one vendor at a time.
