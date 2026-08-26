---
id: esp32-h4
type: soc
vendor: espressif
name: ESP32-H4
cpu:
  arch: risc-v
  cores: 2
  max_mhz: 96
  extensions:
  - dsp
memory:
  sram_kb: 384
  rom_kb: 128
  psram_external: true
radios:
  wifi: null
  bluetooth:
    le: '5.4'
    classic: false
    features:
    - le-audio
    - iso-channels
    - pawr
    - direction-finding-aoa-aod
  ieee802154:
    present: true
    protocols:
    - thread-1.4
    - zigbee-3.0
usb:
  native: true
  type: otg
security:
- secure-boot
- memory-encryption
- ecdsa-ds
- crypto-accelerators
- trng
drive:
  gpio_pads_total: 40
notes:
- No Wi-Fi radio
- Product page notes Bluetooth 6.0 certification; functional core spec is BLE 5.4
- 'Ultra-low-power: integrated DC-DC, multiple low-power modes'
- No public datasheet or Hardware Design Guidelines page exists yet for ESP32-H4
  (checked 2026-08-26) — drive currents and reserved_pins omitted, not guessed.
  gpio_pads_total=40 is the product-page GPIO count for the bare-die SKUs.
sources:
- field: '*'
  url: https://www.espressif.com/en/products/socs/esp32-h4
  verified: '2026-08-21'
- field: drive
  url: https://www.espressif.com/en/products/socs/esp32-h4
  verified: '2026-08-26'
---

# ESP32-H4

Newest H-series: **no Wi-Fi**, dual-core, and the **highest Bluetooth in the family — BLE 5.4 with LE Audio, ISO channels, PAwR, and Direction Finding (AoA/AoD)** — plus 802.15.4. Ultra-low-power for coin-cell devices.
