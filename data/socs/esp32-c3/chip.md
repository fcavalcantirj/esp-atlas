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
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 22
reserved_pins:
  strapping:
  - 2
  - 8
  - 9
  usb_flash_tied:
  - 18
  - 19
notes:
- Datasheet states 'Bluetooth 5' without a printed sub-revision
- 22 GPIOs on QFN32 (16 on QFN28).
- 'Default drive strength: GPIO2/3/4(MTMS)/5(MTDI) = 10 mA, GPIO18/19 (USB) =
  40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.pdf
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.pdf
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-C3

Budget RISC-V workhorse: Wi-Fi 4 + BLE 5, native USB Serial/JTAG. Very widely supported in Arduino & ESP-IDF.
