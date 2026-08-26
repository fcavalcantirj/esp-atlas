---
id: esp32
type: soc
vendor: espressif
name: ESP32
cpu:
  arch: xtensa-lx6
  cores: 2
  max_mhz: 240
memory:
  sram_kb: 520
  rtc_sram_kb: 16
  rom_kb: 448
  psram_external: true
radios:
  wifi:
    standard: wifi-4
    bands_ghz:
    - 2.4
  bluetooth:
    le: '4.2'
    classic: true
    features:
    - dual-mode
  ieee802154:
    present: false
usb:
  native: false
security:
- secure-boot-v1
- flash-encryption
- aes
- sha-2
- rsa
- rng
reserved_pins:
  strapping:
  - 0
  - 2
  - 5
  - 12
  - 15
  input_only:
  - 34
  - 35
  - 36
  - 39
  usb_flash_tied:
  - 6
  - 7
  - 8
  - 9
  - 10
  - 11
notes:
- Wi-Fi promiscuous mode supported
- Secure Boot v2 only on chip rev v3.0+
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32_datasheet_en.pdf
  verified: '2026-08-21'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32

The original. The only chip in the family with **Bluetooth Classic (BR/EDR)** — dual-mode with BLE. Not recommended for new designs unless you specifically need Classic.
