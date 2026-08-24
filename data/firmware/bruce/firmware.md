---
id: bruce
type: firmware
name: Bruce
url: https://github.com/pr3y/Bruce
category: pentest
maintainer: pr3y
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
sources:
- field: '*'
  url: https://github.com/pr3y/Bruce
  verified: '2026-08-24'
- field: 'license'
  url: https://raw.githubusercontent.com/pr3y/Bruce/main/LICENSE
  verified: '2026-08-24'
- field: 'distribution'
  url: https://bruce.computer/flasher
  verified: '2026-08-24'
---

# Bruce

Bruce is a versatile ESP32 firmware packed with offensive-security tools, built for portable
Red Team work. It runs on a range of M5Stack and LILYGO devices, and installs from the project's
own web flasher, from GitHub release binaries, or from the M5Burner store.
