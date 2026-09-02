# esp-atlas — Verify my board (the debug rail)

> Extends `SPEC.md` and complements `SPEC-wizard.md`'s Flash Wizard (#43). Where
> the flash rail writes firmware to a board, this rail **reads** the board back
> and checks esp-atlas's own cited record against it. Same core principle as
> everywhere else in esp-atlas: the site is a pure function of a cited dataset —
> here, the dataset under test is the live chip itself.

## Purpose

The tagline says "flash it, debug it." Flashing shipped in P2b. This spec is
**debug it** — "Verify my board," a client-side-only rail (browser ↔ USB over
Web Serial, no backend involved) with two parts on every board page:

- **Rail A — VERIFY**: connect to the board, ask the silicon what it actually
  is, and compare that reading against the board record esp-atlas cites
  (`soc`, `flash_mb`, `psram_mb`). Per field: **match**, **mismatch**, or
  **unknown**.
- **Rail B — SERIAL MONITOR**: open the port and stream whatever the firmware
  prints, live, in a scrollable console — the plain "watch it run" debug loop.

## Grounding principle

Verify checks **cited** specs against **live** silicon. It never asserts
anything beyond what the chip itself returned in this session:

- A field the chip didn't return (a read failed, or the connection dropped
  first) renders **unknown**, not a guess and not silence.
- A field esp-atlas has no cited value for (e.g. a record missing `psram_mb`)
  also renders **unknown** — there is nothing to check the reading against.
- Both readings are always shown side by side (detected vs. cited) — the
  verdict is never color alone, exactly like `TrustTierBadge`.

## Rail A — VERIFY

### Detection

Uses **esptool-js**'s `ESPLoader` over a Web Serial `Transport`, the same
family of tooling ESP Web Tools itself is built on, run directly against the
ROM bootloader (`detectChip()` — no stub firmware upload, no flashing, no
erase; strictly read-only):

**Identification order** (`apps/web/lib/chip-identify.ts`, pure + unit-tested;
`verify-serial.ts` drives it after `connect(…, detecting=false)`):

1. **chip-id** — the `GET_SECURITY_INFO` ROM command's `IMAGE_CHIP_ID`,
   revision-independent (how Python esptool ≥ 4.9 identifies every chip since
   the C3; ESP8266/ESP32/S2 never answer it).
2. **magic** — the `CHIP_DETECT_MAGIC` register against esptool-js's per-chip
   table. A snapshot: newer silicon answers values it has never seen — an
   ESP32-C5 rev v1.2 (ROM eco3-20250704) answers `0x30e1706f`, absent from
   esptool-js 0.6.1, and `detectChip()` alone died with "Unexpected CHIP magic
   value" (2026-09-01).
3. **assumed** — nothing matched; on a board page the human may click to
   proceed on the cited SoC. The reading is labelled *assumed*, the matcher
   renders that row `unknown` (never `match`), and the unknown magic/chip-id
   are shown so they can be reported upstream. `/debug` (no record) stops at 2
   and points at the board page.

A chip identified by chip-id whose magic is unknown gets a note: in-browser
flashers built on the same table (ESP Web Tools, web.esphome.io) will refuse it
— flash from a terminal. Upstream esptool-js merged chip-id detection on
2026-09-01 (#197, unreleased); when a release ships it, step 1 may lean on
`connect()` again — the order and its tests stay.

| Reading | esptool-js source | Shape |
|---|---|---|
| Chip family | `loader.chip.CHIP_NAME` (e.g. `"ESP32-S3"`) | lowercased, matches esp-atlas SoC ids (`esp32-s3`) 1:1 |
| Flash size | `loader.detectFlashSize()` (e.g. `"8MB"`) | parsed to whole MB |
| PSRAM | `loader.chip.getChipFeatures(loader)` — string array; scanned case-insensitively for `"psram"`, with a `"N MB"` size pulled out when the chip's own feature string states one (e.g. ESP32-S3's `"Embedded PSRAM 8MB"`; plain ESP32 only ever says `"Embedded PSRAM"`, no size) | `{ present: boolean, sizeMb: number \| null }` |
| MAC | `loader.chip.readMac(loader)` | `"aa:bb:cc:dd:ee:ff"`, informational only — esp-atlas cites no per-unit MAC, so this is never verified, only displayed |

### The matcher (pure, unit-tested)

`apps/web/lib/verify-board.ts` exports `matchBoard(detected, board)`, a pure
function with **no I/O** — it never touches Web Serial, `esptool-js`, or the
DOM, which is what makes it unit-testable outside a browser:

```ts
matchBoard(
  detected: DetectedChip,   // what the silicon said this session
  board: BoardRecord,       // { soc, flashMb, psramMb } — what esp-atlas cites
): VerifyResult              // { fields: FieldResult[], mac, overall }
```

Each `FieldResult` is `{ name, detected, cited, verdict }` with
`verdict: "match" | "mismatch" | "unknown"` for **Chip family**, **Flash
size**, and **PSRAM**. `overall` is `"mismatch"` if any field mismatches,
`"match"` only if every field matches, else `"unknown"`.

Field rules:
- **Chip family** — case-insensitive string equality; `unknown` if either
  side is absent.
- **Flash size** — MB equality; `unknown` if either side is absent.
- **PSRAM** — `0` cited means "no PSRAM"; a detected absence matches a `0`
  cite and mismatches any positive cite (and vice versa). When PSRAM is
  present on both sides but the chip's own feature string didn't state an
  exact size, presence-only agreement still counts as `match` — esp-atlas
  never claims a size reading it doesn't have. `unknown` if either side
  wasn't read/cited at all.

### UI

`components/verify/VerifyBoard.tsx`, mounted on the board page next to the
firmware/flash section (`PartDetailView`), gated behind a click — no
auto-connect on page load, matching the flash rail's own consent-gated
pattern:

1. **"Verify my board"** button → `navigator.serial.requestPort()` (browser's
   own port picker) → `ESPLoader.detectChip()` → the reading feeds
   `matchBoard()` → a per-field verdict card, reusing the flash rail's
   existing card/badge/panel styles (`flash-panel`, `tier-badge`-style dot
   badges) — **no new visual system**.
2. **Graceful failure modes**, all worded honestly rather than silenced:
   - No Web Serial in this browser (non-Chromium) → a static note asking for
     Chrome/Edge on desktop, same wording style as the flash rail's
     `unsupported` slot.
   - User dismisses the browser's port-picker dialog → nothing happens, no
     error toast (`NotFoundError` from `requestPort()` is swallowed silently
     — declining the picker is not a failure).
   - A read fails mid-detect (device unplugged, wrong port, timeout) → the
     panel shows what *was* read as `unknown`/absent for the rest, plus one
     plain-language error line, never a stack trace.

## Rail B — SERIAL MONITOR

Same component, same connected `Transport` (or a fresh one if the user opens
the monitor without running Verify first) — a second, independent action:

- Baud rate selector, default **115200** (ESP32 bootloader logging's near-
  universal default); common alternates offered (74880, 9600, 921600).
- **Connect** opens the port and streams decoded UTF-8 text into a
  scrollable, monospace console as it arrives — no parsing, no filtering,
  exactly what the firmware wrote to UART.
- **Clear** empties the console without touching the connection.
- **Disconnect** closes the port; the console keeps its last contents until
  the panel is closed or reopened.
- This rail has no cited/verified data to check, so it renders no verdicts —
  it is pure observation, not this spec's Rail A comparison logic in another
  package.

## Scope v1

Both rails ship together. Explicitly **out of scope for v1** (tracked in
`ROADMAP.md`'s Future section): per-board GPIO pinout / JTAG step-through
debugging.

## Dependency: esptool-js, pinned

`esp-web-tools.ts` pins its dependency to an exact version loaded from a
pinned CDN URL because code that writes firmware to hardware must not change
behaviour underneath esp-atlas. `esptool-js` carries the same risk surface
(it drives a chip's ROM bootloader over serial) but ships as a plain ESM
library (no custom element to attach), so — unlike ESP Web Tools — it is
added as an ordinary, **exact-pinned** (no `^`/`~`) `dependencies` entry in
`apps/web/package.json`, resolved and locked by `package-lock.json` exactly
like every other pinned dependency in the repo:

```json
"esptool-js": "0.6.1"
```

The `VerifyBoard` component `import()`s it dynamically (`await
import("esptool-js")`) inside the click handler, mirroring `ensureEspWebTools()`'s
"only pages that open a panel pay for it" rule — the board page's initial JS
bundle carries zero bytes of `esptool-js` until a human clicks "Verify my
board."

## Testability

- **Pure and unit-tested (TDD):** `lib/verify-board.ts`'s `matchBoard()` —
  the field-comparison logic — covering match, mismatch (chip family, flash
  size), the `psram 0` vs. `psram >0` mismatch in both directions, and
  `unknown` (missing detected reading, missing cited value). Run with
  `npm --prefix apps/web test` (Node's built-in `node --test` against
  `apps/web/lib/*.test.ts` — no new test framework dependency).
- **Browser-only, not unit-tested:** everything that touches
  `navigator.serial` or `esptool-js`'s `Transport`/`ESPLoader` I/O. This is
  isolated behind `DetectedChip`/`matchBoard()`'s pure boundary so the
  matcher tests need no browser and no mocked Web Serial API (mocking
  Web Serial would test the mock, not the code). The I/O path is verified by
  `tsc --noEmit`, `eslint`, `next build`, and manual hardware testing — never
  by faked browser snapshots.
