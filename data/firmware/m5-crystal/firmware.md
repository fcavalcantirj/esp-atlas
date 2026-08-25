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
sources:
- field: '*'
  url: https://github.com/Dlazder/m5_crystal_firmware
  verified: '2026-08-23'
---

# M5 Crystal

M5 Crystal is a Wi-Fi/BLE/NFC/IR pentesting firmware for M5Stack devices.
