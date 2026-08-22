<!--
  board template — copy to data/boards/<brand>/<board-id>/board.md

  Before filling this in:
    1. esp-atlas search "<board name>"   # make sure it doesn't already exist
    2. Read schema/board.schema.json — it is the authoritative contract, this
       template just mirrors it with inline notes.
    3. Do NOT restate the module's (or soc's) cpu/radio/flash specs here — they're
       inherited via `module:`/`soc:`. Only describe what the board *adds*
       (USB, power, display, headers, onboard peripherals).
    4. Fill every field you can back with an official source; delete every
       field you can't verify (source-or-omit, no exceptions).
    5. esp-atlas validate data/boards/<brand>/<board-id>/board.md   before opening a PR.
-->
---
# id: kebab-case, MUST equal the folder name this file lives in
# (data/boards/lilygo/lilygo-t-display-s3/board.md -> id: lilygo-t-display-s3).
id: REPLACE-ME

# type: literal "board", do not change.
type: board

# brand: the board vendor/maker — MUST equal the brand folder this file lives
# under (data/boards/lilygo/... -> brand: lilygo). Source: product page.
brand: REPLACE-ME

# name: the board's marketing/part name, e.g. "T-Display-S3".
# Source: product page or datasheet cover.
name: REPLACE-ME

# aka (optional): alternate names/spellings this board is also known by.
# aka:
# - ALT-NAME

# Exactly one of `module` or `soc` is required — whichever the board actually
# uses. Prefer `module:` when the board uses a packaged module; use `soc:` only
# for bare-chip boards. The id MUST already exist under data/modules/ or data/socs/.

# module (required unless `soc` is set): id of the module this board uses.
# module: REPLACE-ME

# soc (required unless `module` is set): id of the bare SoC this board uses.
# soc: REPLACE-ME

# form_factor (optional): e.g. "dev", "xiao", "feather". Source: product page.
# form_factor: dev

# dimensions_mm (optional): [width, length] or [width, length, height] in mm.
# Source: product page mechanical drawing/spec sheet.
# dimensions_mm:
# - 0.0
# - 0.0

# usb (optional): onboard USB. connector: usb-c | micro-usb | mini-usb | none.
# bridge: the USB-UART bridge chip (e.g. cp2102, ch340), or "native" if the
# SoC's own USB is used directly. Source: product page or schematic.
# usb:
#   connector: usb-c
#   bridge: native

# power (optional): onboard battery support. Source: product page or schematic.
# power:
#   battery_connector: true
#   charging: true

# display (optional): free-text display spec, e.g. "1.9in 170x320 IPS ST7789V".
# Only set if the board has an onboard display. Source: product page.
# display: REPLACE-ME

# extras (optional): other onboard peripherals — sd-card, imu, mic, rgb-led,
# gps, etc. Source: product page or schematic.
# extras:
# - sd-card

# notes (optional): free-text clarifications (variants, caveats). Not a source
# substitute for hard specs.
# notes:
# - free text note

# sources (required, minItems 1): one entry per verified field or field group.
# field: '*' covers the whole record; or a dotted path for a specific field.
# url: the official product page or datasheet. verified: ISO date you checked it.
sources:
- field: '*'
  url: REPLACE-ME
  verified: 'YYYY-MM-DD'
---

# REPLACE-ME

One or two sentences: what module/soc this board is built on, its standout
feature (display, battery, form factor), and its connector type.
