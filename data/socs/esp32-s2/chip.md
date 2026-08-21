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
notes:
- 802.11mc FTM ranging
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-s2_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-S2

Single-core Wi-Fi chip with full-speed native USB OTG and **no Bluetooth radio at all**. Largely superseded by the S3 for new designs.
