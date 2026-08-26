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
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 19
reserved_pins:
  strapping:
  - 8
  - 9
  - 25
  usb_flash_tied:
  - 26
  - 27
notes:
- No Wi-Fi radio — 802.15.4 + BLE only
- No in-package flash pins bonded out as GPIOs.
- 'Default drive strength: GPIO26/27 (USB) = 40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-h2_datasheet_en.html
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp32-h2_datasheet_en.html
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32h2/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-H2

**No Wi-Fi.** A dedicated 802.15.4 (Thread / Zigbee / Matter) + BLE 5.3 endpoint chip for low-power mesh sensors.
