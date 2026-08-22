<!--
  soc template — copy to data/socs/<soc-id>/chip.md

  Before filling this in:
    1. esp-atlas search "<chip name>"   # make sure it doesn't already exist
    2. Read schema/soc.schema.json — it is the authoritative contract, this
       template just mirrors it with inline notes.
    3. Fill every field you can back with an official source; delete every
       field you can't verify (source-or-omit, no exceptions).
    4. esp-atlas validate data/socs/<soc-id>/chip.md   before opening a PR.
-->
---
# id: kebab-case, MUST equal the folder name this file lives in
# (data/socs/esp32-s3/chip.md -> id: esp32-s3). Source: not applicable (structural).
id: REPLACE-ME

# type: literal "soc", do not change.
type: soc

# vendor: the silicon vendor, e.g. "espressif". Source: datasheet cover page.
vendor: espressif

# name: the chip's marketing/part name as printed on the datasheet, e.g. "ESP32-S3".
# Source: datasheet cover page or product page.
name: REPLACE-ME

# aka (optional): alternate names/spellings this chip is also known by.
# Source: same datasheet, or vendor product page listing aliases.
# aka:
# - ALT-NAME

# cpu (required): core architecture and clock. Source: datasheet "CPU" section.
cpu:
  # arch: one of xtensa-lx6 | xtensa-lx7 | risc-v — exact match required.
  arch: REPLACE-ME
  # cores: integer core count.
  cores: 0
  # max_mhz: max clock speed in MHz.
  max_mhz: 0
  # extensions (optional): notable ISA extensions, e.g. simd-vector.
  # extensions:
  # - simd-vector
  # lp_core (optional): low-power co-processor, if the chip has one.
  # lp_core:
  #   arch: risc-v
  #   max_mhz: 0

# memory (required): on-chip memory. Source: datasheet "Memory" section.
memory:
  # sram_kb: required, on-chip SRAM in KB.
  sram_kb: 0
  # lp_sram_kb / rtc_sram_kb (optional): low-power/RTC domain SRAM in KB.
  # lp_sram_kb: 0
  # rtc_sram_kb: 0
  # rom_kb (optional): mask ROM in KB.
  # rom_kb: 0
  # in_package_psram_mb (optional): PSRAM options integrated in the package (list of MB sizes).
  # in_package_psram_mb:
  # - 8
  # psram_external (optional): true if PSRAM is only available as an external chip.
  # psram_external: true

# radios (optional but usually present): every present radio needs its own
# sources: entry (dotted path, e.g. radios.wifi / radios.bluetooth / radios.ieee802154).
# Omit a radio entirely (or set it to null) rather than guessing its specs.
radios:
  # wifi:
  #   standard: wifi-4  # or wifi-6
  #   bands_ghz:
  #   - 2.4
  # bluetooth:
  #   le: '5'          # BLE core version exactly as printed by the datasheet
  #   classic: false   # Bluetooth Classic (BR/EDR) support
  #   features: []
  # ieee802154:
  #   present: false
  #   protocols: []

# usb (optional): only if the chip has native USB.
# usb:
#   native: true
#   type: otg-full-speed + serial-jtag

# interfaces (optional): peripheral interfaces, e.g. spi, i2c, uart, i2s, sdio.
# interfaces:
# - spi

# security (optional): security features as listed by the datasheet.
# security:
# - secure-boot-v2
# - flash-encryption

# notes (optional): free-text clarifications that don't fit a structured field
# (variant differences, caveats). Not a source substitute for hard specs.
# notes:
# - free text note

# sources (required, minItems 1): one entry per verified field or field group.
# field: '*' covers the whole record; or a dotted path like radios.bluetooth.
# url: the official datasheet or vendor page. verified: ISO date you checked it.
sources:
- field: '*'
  url: REPLACE-ME
  verified: 'YYYY-MM-DD'
---

# REPLACE-ME

One or two sentences: what this chip is, its standout capability, and how it
differs from its closest siblings in the family.
