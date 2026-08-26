---
id: esp32-c2
type: soc
vendor: espressif
name: ESP32-C2
aka:
- ESP8684
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 120
memory:
  sram_kb: 272
  rom_kb: 576
radios:
  wifi:
    standard: wifi-4
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.3'
    classic: false
  ieee802154:
    present: false
usb:
  native: false
security:
- secure-boot
- flash-encryption-xts-aes
- ecc
- sha
- rng
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 14
reserved_pins:
  strapping:
  - 8
  - 9
notes:
- No standalone AES/RSA accelerator or DS peripheral (unlike C3/C6)
- No native USB; in-package flash pins are not bonded out as GPIOs.
- Default drive strength is 20 mA for all pins.
sources:
- field: '*'
  url: https://documentation.espressif.com/esp8684_datasheet_en.pdf
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp8684_datasheet_en.pdf
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c2/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-C2

The most cost-reduced member, an ESP8266 replacement. RISC-V, Wi-Fi 4 + BLE 5.3, no native USB.
