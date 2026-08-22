<!--
  module template — copy to data/modules/<module-id>/module.md

  Before filling this in:
    1. esp-atlas search "<module name>"   # make sure it doesn't already exist
    2. Read schema/module.schema.json — it is the authoritative contract, this
       template just mirrors it with inline notes.
    3. Do NOT restate the soc's cpu/radio specs here — they're inherited via `soc:`.
       Only describe what the module *adds* (flash, PSRAM, antenna, certs, size).
    4. Fill every field you can back with an official source; delete every
       field you can't verify (source-or-omit, no exceptions).
    5. esp-atlas validate data/modules/<module-id>/module.md   before opening a PR.
-->
---
# id: kebab-case, MUST equal the folder name this file lives in
# (data/modules/esp32-s3-wroom-1/module.md -> id: esp32-s3-wroom-1).
id: REPLACE-ME

# type: literal "module", do not change.
type: module

# vendor: the module manufacturer, e.g. "espressif". Source: datasheet cover page.
vendor: espressif

# name: the module's marketing/part name, e.g. "ESP32-S3-WROOM-1".
# Source: datasheet cover page or product page.
name: REPLACE-ME

# aka (optional): alternate names/spellings this module is also known by.
# aka:
# - ALT-NAME

# soc (required): id of the SoC this module is built on — MUST already exist
# under data/socs/<that-id>/chip.md. This is how radio/cpu specs are inherited;
# do not re-type them below. Source: same datasheet, "based on <chip>" section.
soc: REPLACE-ME

# flash_mb (optional): onboard flash size in MB (baseline variant).
# Source: datasheet ordering/variant table.
# flash_mb: 0

# psram_mb (optional): onboard PSRAM size in MB, if the baseline variant has one.
# Source: datasheet ordering/variant table.
# psram_mb: 0

# antenna (optional): one of pcb | ipex | pcb+ipex | none. Source: datasheet
# "Antenna" section or product page.
# antenna: pcb

# dimensions_mm (optional): [width, length] or [width, length, height] in mm.
# Source: datasheet mechanical drawing.
# dimensions_mm:
# - 0.0
# - 0.0

# certifications (optional): regulatory/compliance marks, e.g. fcc, ce, reach, rohs.
# Source: datasheet compliance section or vendor certification page.
# certifications:
# - reach
# - rohs

# notes (optional): free-text clarifications (variant differences, sibling
# modules, caveats). Not a source substitute for hard specs.
# notes:
# - free text note

# sources (required, minItems 1): one entry per verified field or field group.
# field: '*' covers the whole record; or a dotted path for a specific field.
# url: the official datasheet or vendor page. verified: ISO date you checked it.
sources:
- field: '*'
  url: REPLACE-ME
  verified: 'YYYY-MM-DD'
---

# REPLACE-ME

One or two sentences: what SoC this module wraps, its radio/flash/PSRAM
headline, and its antenna type.
