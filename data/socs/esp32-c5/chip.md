---
id: esp32-c5
type: soc
vendor: espressif
name: ESP32-C5
cpu:
  arch: risc-v
  cores: 1
  max_mhz: 240
  lp_core:
    arch: risc-v
    max_mhz: 48
memory:
  sram_kb: 384
  lp_sram_kb: 16
  rom_kb: 320
radios:
  wifi:
    standard: wifi-6
    bands_ghz:
    - 2.4
    - 5
  bluetooth:
    le: '5'
    classic: false
  ieee802154:
    present: true
    protocols:
    - thread-1.4
    - zigbee-3.0
usb:
  native: true
  type: serial-jtag
security:
- secure-boot
- flash-psram-encryption-xts-aes
- aes-256
- sha
- rsa
- ecc
- hmac
- rsa-ecdsa-ds
- trng
- key-manager
- apm
- tee
- glitch-detector
drive:
  gpio_source_ma_max: 40
  gpio_sink_ma_max: 28
  gpio_pads_total: 29
reserved_pins:
  strapping:
  - 2
  - 3
  - 7
  - 25
  - 26
  - 27
  - 28
  usb_flash_tied:
  - 13
  - 14
notes:
- First Espressif chip with 5 GHz Wi-Fi (5180-5885 MHz)
- Datasheet notes 'Bluetooth Core 6.0 certified'; product page markets 'BLE 5' — BLE-only
  either way
- 'Default drive strength: GPIO13/14 = 40 mA, others 20 mA.'
sources:
- field: '*'
  url: https://documentation.espressif.com/esp32-c5_datasheet_en.html
  verified: '2026-08-21'
- field: drive
  url: https://documentation.espressif.com/esp32-c5_datasheet_en.html
  verified: '2026-08-26'
- field: reserved_pins
  url: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c5/schematic-checklist.html
  verified: '2026-08-26'
---

# ESP32-C5

The **only** ESP with **dual-band Wi-Fi 6 (2.4 + 5 GHz)**. Also BLE + 802.15.4 (Thread 1.4 / Zigbee 3.0). The pick when you must touch 5 GHz.
