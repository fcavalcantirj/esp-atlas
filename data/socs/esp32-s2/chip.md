---
id: esp32-s2
type: soc
vendor: espressif
name: ESP32-S2
cpu:
  arch: xtensa-lx7
  cores: 1
  max_mhz: 240
memory:
  sram_kb: 320
  rtc_sram_kb: 16
  rom_kb: 128
  psram_external: true
radios:
  wifi:
    standard: wifi-4
    bands_ghz:
    - 2.4
  bluetooth: null
  ieee802154:
    present: false
usb:
  native: true
  type: otg-full-speed
security:
- secure-boot-v2
- flash-encryption
- aes-256
- sha
- rsa
- hmac
- ds-peripheral
- rng
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 43
reserved_pins:
  strapping:
  - 0
  - 45
  - 46
  input_only:
  - 46
  usb_flash_tied:
  - 19
  - 20
notes:
- 802.11mc FTM ranging
- Default drive strength is 20 mA for all pins (abs-max 40 mA source / 28 mA
  sink).
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-s2_datasheet_en.pdf
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp32-s2_datasheet_en.pdf
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s2/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-S2

Single-core Wi-Fi chip with full-speed native USB OTG and **no Bluetooth radio at all**. Largely superseded by the S3 for new designs.
