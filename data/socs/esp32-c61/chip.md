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
notes:
- No 802.15.4 despite the C-series naming
- Datasheet notes 'Bluetooth Core 6.0 certified' (BLE-only)
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c61_datasheet_en.html
  verified: '2026-08-21'
---

# ESP32-C61

Budget Wi-Fi 6 (2.4 GHz only). BLE-only, and notably **no 802.15.4** — do not confuse with the C6.
