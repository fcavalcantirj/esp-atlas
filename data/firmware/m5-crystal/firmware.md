---
id: m5-crystal
type: firmware
name: M5 Crystal
url: https://github.com/Dlazder/m5_crystal_firmware
category: pentest
maintainer: Dlazder
socs:
- esp32
- esp32-s3
distribution:
- m5burner
- releases
capabilities:
- wifi
- ble
- nfc
- ir
requires:
- capability: wifi
  board_signal: radio-wifi
- capability: ble
  board_signal: radio-ble
- capability: rfid-nfc
  why: NFC tool needs an on-board reader
  board_signal: null
- capability: ir
  why: IR tool needs an IR LED
  board_signal: null
not_required:
- capability: psram
popularity:
  stars: 84
  forks: 3
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-09-01'
- field: summary
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-09-20'
summary: "M5 Crystal is a multifunctional firmware for M5Stack devices that combines\
  \ pentesting capabilities\u2014such as Wi\u2011Fi attacks, Bluetooth scanning, NFC\
  \ read/write, IR control, and BadUSB\u2014with everyday utilities like file management,\
  \ web server, and customizable settings, all presented in a multilingual interface."
readme_lang: en
readme_sha: 27c67119945fec7f74da27d8aa8b488106f314f096b3d9c3b4c47b00821482e3
---

# M5 Crystal

M5 Crystal is a Wi-Fi/BLE/NFC/IR pentesting firmware for M5Stack devices.
