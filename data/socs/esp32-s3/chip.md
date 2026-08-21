---
id: esp32-s3
type: soc
vendor: espressif
name: ESP32-S3
cpu:
  arch: xtensa-lx7
  cores: 2
  max_mhz: 240
  extensions:
  - simd-vector
memory:
  sram_kb: 512
  rtc_sram_kb: 16
  rom_kb: 384
  psram_external: true
radios:
  wifi:
    standard: wifi-4
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5'
    classic: false
  ieee802154:
    present: false
usb:
  native: true
  type: otg-full-speed + serial-jtag
security:
- secure-boot-v2
- flash-encryption
- aes
- sha
- rsa
- hmac
- rsa-ds
- rng
- clock-glitch-detection
notes:
- 802.11mc FTM ranging
- SIMD for on-device ML/DSP
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-s3_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-S3

Dual-core with SIMD/vector instructions for AI/DSP (TinyML), native USB OTG, and the largest GPIO count — the versatile all-rounder. BLE 5, no Classic.
