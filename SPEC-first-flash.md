# SPEC — First Flash

> Get a person with a brand-new ESP32 from *board-in-hand* to *flashing* — or, when it
> fails, fix the **actual** blocker (cable / driver / download mode) with board-specific
> steps. Not a new silo: the connective spine over the tools we already have, plus the
> one piece of data we're missing.

**Origin:** Felipe plugged in a brand-new **ESP32-C5-DevKitC-1**, opened esp-atlas, and
could do nothing actionable — no loud "I have a board" entry, and nothing told him the
board-specific way to enter download/flash mode (the #1 first-flash blocker). Board is
catalogued (`data/boards/espressif/esp32-c5-devkitc-1`) and is the acceptance target.

---

## Non-goals
- **Not a 4th page.** Wizard = *shop by capability*; Debug = *detect chip + serial*;
  board pages = *full verify*. Detection (`VerifyBoard` / `verify-serial.ts`) already
  exists and is unit-tested. This spec **connects** those and adds the missing data +
  the troubleshooter + a loud front door — it does not rebuild them.

## The three layers

### A. Data — the missing knowledge (cited, motto-clean)
New per-board fields in `schema/board.schema.json`, each **cite-or-omit** to the board's
own user guide (never guessed — hardware steps must be verifiable):
- `download_mode`: `{ mode: "auto" | "manual", steps?: string, note?: string }`
  - `auto` — USB-serial bridge toggles EN/IO0 via DTR/RTS; just click flash.
  - `manual` — the exact sequence, e.g. *"hold **BOOT/IO0**, tap **RESET/EN**, release BOOT."*
- `usb_serial`: e.g. `native-usb-serial-jtag | cp2102 | cp2102n | ch340 | ch343` — drives
  which **driver** the troubleshooter recommends.
- `first_flash_notes` *(optional)* — board-specific gotchas, cited. **Shipped 2026-09-01**:
  the C5-DevKitC-1 and C6-DevKitC-1 cite their J5 current-measurement jumper (a unit
  shipped without it — USB bridge enumerated, power LED lit, chip unpowered on both
  ports; no cable/driver/download-mode step could find that). `GET /api/boards/boot`
  returns it; the troubleshooter renders a "check the power jumper" step from it.
Guard-gated (schema + sources-live). Jr backfills over time; **seed C5-DevKitC-1 + top
boards first**, cited to Espressif's ESP32-C5-DevKitC-1 user guide.

### B. Flow — `🔌 Plug my board` (the loud CTA)
- Fixed high-contrast header button on all content pages.
- Click → Web Serial detect (reuse `VerifyBoard`) → read chip → identify candidate
  board(s) → show **verified specs + flash recipe + a copy-paste "bot instructions"
  block** (exact esptool/CLI + agent-ready steps for *this* board).
- Chrome/Edge only (Web Serial); graceful fallback message elsewhere.

### C. Troubleshooter — the failure path (the part that actually saves people)
When detect/connect fails (no port / no chip / timeout):
1. **Cable** — data cable, not power-only.
2. **Driver** — for this board's `usb_serial` chip → link + how to check.
3. **Enter download mode → `<this board's download_mode.steps>`** (from the data; generic
   ESP32 sequence if the board is unknown).
4. **Retry.**
Every step sourced from board data — no guessed hardware instructions, ever.

## Reuse (don't rebuild)
`VerifyBoard.tsx`, `verify-serial.ts` (detect + match, already tested); Debug (detect-only)
and board pages (full verify) stay as-is. This spine wires them together and adds C + the
bot-instructions block + the loud entry.

## Phasing
- **P0 — Data.** `download_mode` + `usb_serial` schema fields; populate C5-DevKitC-1 (cited); guard green. *(bot/data only — no site.)*
- **P1 — Spine.** `🔌 Plug my board` header entry → detect → identify → specs + recipe + bot-instructions.
- **P2 — Troubleshooter.** Failure path with board-specific download-mode + driver/cable.
- **P3 — Scale.** Jr backfills `download_mode`/`usb_serial` across boards.

## Acceptance test (Felipe's board)
Chrome desktop: plug **ESP32-C5-DevKitC-1** → click `🔌 Plug my board` → it identifies the
board, shows specs + recipe + copy-paste flash/bot instructions. If connect fails, the
troubleshooter shows the C5-DevKitC-1's **exact** download-mode + driver steps. **Not done
until Felipe flashes his board through this flow.**

## Deploy rule
No `apps/` (public site) change deploys without Felipe's explicit go; he reviews it before
it ships to production. Data/bot layers (P0, P3) stay on the normal latitude.
