---
id: esp32-c6
type: soc
vendor: espressif
name: ESP32-C6
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 160
  lp_core:
    arch: risc-v
    max_mhz: 20
memory:
  sram_kb: 512
  lp_sram_kb: 16
  rom_kb: 320
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.3'
    classic: false
  ieee802154:
    present: true
    protocols:
    - zigbee-3.0
    - thread-1.3
    - matter
usb:
  native: true
  type: serial-jtag
security:
- secure-boot
- flash-encryption-xts-aes
- aes-256
- ecc
- hmac
- rsa
- sha
- rsa-ds
- rng
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 30
reserved_pins:
  strapping:
  - 8
  - 9
  - 10
  - 11
  - 15
  usb_flash_tied:
  - 12
  - 13
notes:
- Wi-Fi / BLE / 802.15.4 coexist on a shared antenna
- 'Default drive strength: GPIO12/13 = 40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-21'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/schematic-checklist.html
  verified: '2026-08-26'
- field: drive
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-26'
---

# ESP32-C6

The IoT all-rounder: **Wi-Fi 6 + BLE 5.3 + 802.15.4 (Zigbee 3.0 / Thread 1.3 / Matter)** in one chip, plus a low-power RISC-V core. The single-chip smart-home pick.
