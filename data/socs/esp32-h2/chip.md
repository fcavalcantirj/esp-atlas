---
id: esp32-h2
type: soc
vendor: espressif
name: ESP32-H2
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 96
memory:
  sram_kb: 320
  lp_sram_kb: 4
  rom_kb: 128
radios:
  wifi: null
  bluetooth:
    le: '5.3'
    classic: false
  ieee802154:
    present: true
    protocols:
    - thread-1.4
    - zigbee-3.0
    - matter
usb:
  native: true
  type: serial-jtag
security:
- ecc-secure-boot
- flash-encryption-aes-256-xts
- ecdsa-ds
- hmac
- crypto-accelerators
notes:
- No Wi-Fi radio — 802.15.4 + BLE only
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-h2_datasheet_en.html
  verified: '2026-08-21'
---

# ESP32-H2

**No Wi-Fi.** A dedicated 802.15.4 (Thread / Zigbee / Matter) + BLE 5.3 endpoint chip for low-power mesh sensors.
