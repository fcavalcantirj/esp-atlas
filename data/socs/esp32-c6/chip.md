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
notes:
- Wi-Fi / BLE / 802.15.4 coexist on a shared antenna
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-C6

The IoT all-rounder: **Wi-Fi 6 + BLE 5.3 + 802.15.4 (Zigbee 3.0 / Thread 1.3 / Matter)** in one chip, plus a low-power RISC-V core. The single-chip smart-home pick.
