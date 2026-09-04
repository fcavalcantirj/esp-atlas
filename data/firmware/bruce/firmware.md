---
id: bruce
type: firmware
name: Bruce
url: https://github.com/BruceDevices/firmware
category: pentest
maintainer: brucedevices
license: AGPL-3.0
socs:
- esp32
- esp32-s3
- esp32-c5
distribution:
- releases
- web-flasher
- esp-web-tools
- m5burner
capabilities:
- wifi
- ble
- sub-ghz
- rfid-nfc
- ir
- badusb
requires:
- capability: wifi
  why: core Wi-Fi tools, on-chip
  board_signal: radio-wifi
- capability: ble
  why: core BLE tools, on-chip
  board_signal: radio-ble
- capability: native-usb
  why: BadUSB tools need native USB (esp32-s2/s3)
  board_signal: native-usb
- capability: sub-ghz
  why: sub-GHz tools need an on-board CC1101
  board_signal: null
- capability: rfid-nfc
  why: RFID/NFC tools need an on-board PN532
  board_signal: null
- capability: ir
  why: IR tools need an IR LED
  board_signal: null
not_required:
- capability: psram
  why: tool buffers fit SRAM
popularity:
  stars: 6639
  downloads: 69
  as_of: '2026-09-04'
sources:
- field: '*'
  url: https://github.com/BruceDevices/firmware
  verified: '2026-08-24'
- field: license
  url: https://raw.githubusercontent.com/BruceDevices/firmware/main/LICENSE
  verified: '2026-08-24'
- field: distribution
  url: https://bruce.computer/flasher
  verified: '2026-08-24'
- field: popularity
  url: https://github.com/BruceDevices/firmware
  verified: '2026-09-04'
---

# Bruce

Bruce is a versatile ESP32 firmware packed with offensive-security tools, built for portable
Red Team work. It runs on a range of M5Stack and LILYGO devices, and installs from the project's
own web flasher, from GitHub release binaries, or from the M5Burner store.
