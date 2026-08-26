---
id: esp32-c61
type: soc
vendor: espressif
name: ESP32-C61
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 160
  extensions:
  - rv32imac
memory:
  sram_kb: 320
  rom_kb: 256
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5'
    classic: false
  ieee802154:
    present: false
usb:
  native: true
  type: serial-jtag + usb-2.0-fs
security:
- secure-boot
- flash-psram-encryption
- sha-fips-180-4
- ecc-p192-p256
- ecdsa-ds
- trng
- glitch-detector
- tee-pmp
drive:
  gpio_pads_total: 30
reserved_pins:
  strapping:
  - 3
  - 4
  - 7
  - 8
  - 9
  usb_flash_tied:
  - 12
  - 13
notes:
- No 802.15.4 despite the C-series naming
- Datasheet notes 'Bluetooth Core 6.0 certified' (BLE-only)
- No per-pad IOH/IOL table published (only a 1500 mA cumulative IO limit) —
  gpio_source_ma_max/gpio_sink_ma_max omitted, not guessed.
- 'Default drive strength: GPIO12/13 = 40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c61_datasheet_en.html
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp32-c61_datasheet_en.html
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c61/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-C61

Budget Wi-Fi 6 (2.4 GHz only). BLE-only, and notably **no 802.15.4** — do not confuse with the C6.
