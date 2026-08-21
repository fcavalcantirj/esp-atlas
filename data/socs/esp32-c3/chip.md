---
id: esp32-c3
type: soc
vendor: espressif
name: ESP32-C3
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 160
memory:
  sram_kb: 400
  rtc_sram_kb: 8
  rom_kb: 384
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
  type: serial-jtag
security:
- secure-boot
- flash-encryption
- aes-256
- sha
- rsa
- ds-peripheral
- rng
notes:
- Datasheet states 'Bluetooth 5' without a printed sub-revision
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.pdf
  verified: '2026-08-21'
---

# ESP32-C3

Budget RISC-V workhorse: Wi-Fi 4 + BLE 5, native USB Serial/JTAG. Very widely supported in Arduino & ESP-IDF.
