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
notes:
- No standalone AES/RSA accelerator or DS peripheral (unlike C3/C6)
sources:
- field: '*'
  url: https://documentation.espressif.com/esp8684_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-C2

The most cost-reduced member, an ESP8266 replacement. RISC-V, Wi-Fi 4 + BLE 5.3, no native USB.
