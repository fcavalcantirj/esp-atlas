# ESP-Atlas Universe Census — Roadmap

_Last updated: 2026-09-12. Auto-resume scheduled: Monday 2026-09-14 07:00._

## Goal
Map the **whole ESP32 board universe** (hundreds of boards, every tracked brand's full
lineup) and make the coverage gauge **real** — `cataloged ÷ universe`, not `cataloged ÷
what-we-have`. Strict **cite-or-omit** (every board & field traces to a live source; never
fabricate, especially flash/wiring-critical fields). ~2-month horizon, delivered **one board
at a time via the oracle loop, slowly**.

## Mechanism (built, live on main)
- `docs/universe/<brand>.yaml` — committed manifest, **built offline** (like `docs/demand/`,
  never fetched in CI/tick). Each entry: `{board_id, name, mcu, source_url (live-verified),
  status: active|discontinued, note?}`.
- `jr/universe.py` — read-only loader + coverage. `cataloged` is **derived** from
  `data/boards/<brand>/<board_id>/board.md` existence (never a stored flag).
- `docs/universe/coverage.md` — the real gauge, per-brand + overall.
- `SPEC-universe.md` — inclusion boundary + rules.
- ⚠️ The **live tick gauge** (`jr/tick.default_gauge`) is **NOT yet rewired** to the universe
  denominator — deferred until the manifest is complete (the allocator reads `boards_pct`;
  changing it mid-census would destabilize the tick). This is a dedicated late slice.

## Two phases per brand
- **Phase A — enumerate:** the brand's full ESP32 lineup → `docs/universe/<brand>.yaml`,
  every entry with a verified live source.
- **Phase B — author:** the missing `board.md` records, cite-or-omit, in batches of ~5–7.

## Delivery process (the esp-atlas oracle loop)
Worktree off `origin/main` → delegate authors → **gate locally** (`scripts/validate.py` +
`pytest jr/` + **`pytest apps/core/tests`**) → push → PR → **CI is the real oracle**
(`jr-tests`, `tests`, `sources-live`) → `squash-merge --admin`. One board/brand at a time.

### Hard-won lessons (apply every slice)
1. **Authoring touches the CORE catalog** — gate `apps/core/tests` too, not just `jr/`
   (facets/oracle tests read the board set).
2. **Frozen catalog-count tests break as we fill** — robustify them (`== N` → `>= N` or
   filesystem-derived), matching the file's own convention; never weaken intent.
3. **Re-verify source URLs with retries + a browser UA** — some vendor sites (e.g.
   heltec.org) rate-limit and return a transient `000`.
4. New boards need **no firmware mapping** (validate checks orphan firmware, not boards).

## Progress (2026-09-12)
**COMPLETE (mapped + filled):**
- ✅ seeed **5/5**
- ✅ adafruit **26/26**

**ENUMERATED (manifest done, Phase B pending):**
- 🔶 heltec **5/18** (manifest PR #278). 13 to author:
  `heltec-wifi-lora-32-v2`, `heltec-wifi-lora-32-v4`, `heltec-wireless-stick-lite-v3`,
  `heltec-wireless-shell-v3`, `heltec-wireless-bridge`, `heltec-wireless-tracker-v2`,
  `heltec-ht-ct62`, `heltec-esp32-c3`, `heltec-capsule-sensor-v3`, `heltec-e-ink-driver`,
  `heltec-vision-master-e213`, `heltec-vision-master-e290`, `heltec-vision-master-t190`.

**NOT YET ENUMERATED (10 brands):** espressif, m5stack, lilygo, lolin, unexpected-maker,
dfrobot, sparkfun, freenove, elecrow, waveshare.

## Brand gap estimates (arduino-esp32 registry = FLOOR; own-package vendors are higher)
| Brand | have | est. universe | note |
|---|---|---|---|
| waveshare | 2 | ~34 | biggest gap |
| m5stack | 13 | ~40+ | own board package |
| lilygo | 10 | ~30 | many T-* boards |
| lolin/wemos | 6 | ~17 | |
| sparkfun | 5 | ~12 | |
| dfrobot | 6 | ~9 | |
| unexpected-maker | 4 | ~8 | own package |
| freenove / elecrow | 3 / 1 | TBD | |
| espressif | 17 | ~20 | mostly complete |

Catalog today: **107 board records**. True universe estimate: **~250+**.

## Next steps (Monday resume, in order)
1. **Finish Heltec Phase B** — author the 13 missing (batches, oracle loop).
2. **Continue enumerate→author per brand**, biggest-gap-first: waveshare → m5stack →
   lilygo → lolin → sparkfun → dfrobot → unexpected-maker → freenove → elecrow → espressif.
3. When **all brands enumerated** → rewire the live tick gauge to the universe denominator.

## Adjacent status
- **Sources (done):** all boards cite a real doc; 13 vendor doc-URL resolvers in
  `jr/board_doc_resolvers.py`.
- **Field extractors (~tapped):** m5stack + seeed `download_mode` grounded; remaining field
  gaps are sources genuinely silent (correctly omitted, not faked).
- **pinout / `io.gpio_pins`:** its own future spec — ground from **machine-readable board
  defs** (PlatformIO / `pins_arduino.h`), a spike, NOT doc-scraping. Flash/wiring-critical.
- **Jr hourly autonomous loop:** healthy, self-merging, independent of the census.
