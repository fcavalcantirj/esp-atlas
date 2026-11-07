---
id: m5stick-nemo
type: firmware
name: M5Stick NEMO
url: https://github.com/n0xa/m5stick-nemo
category: pentest
maintainer: n0xa
socs:
- esp32
- esp32-s3
distribution:
- m5burner
- releases
capabilities:
- wifi
- ble
- ir
requires:
- capability: wifi
  board_signal: radio-wifi
- capability: ble
  board_signal: radio-ble
- capability: ir
  why: IR tool needs an IR LED
  board_signal: null
not_required:
- capability: psram
popularity:
  stars: 1319
  forks: 210
  as_of: '2026-11-07'
  github_repo_id: 694486730
  github_as_of: '2026-11-07T13:05:00Z'
sources:
- field: '*'
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-09-01'
- field: summary
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-09-20'
- field: popularity.forks
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-11-07'
- field: popularity.github_as_of
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-11-07'
- field: popularity.github_repo_id
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-11-07'
- field: popularity.stars
  url: https://github.com/n0xa/m5stick-nemo
  verified: '2026-11-07'
summary: "M5Stick\u2011NEMO is firmware for M5Stack ESP32 devices (M5Stick\u2011C,\
  \ Stick\u2011C\u2011Plus, Cardputer) that provides a menu\u2011driven suite of prank\
  \ and security\u2011testing tools\u2014including BadUSB detection, BLE/Wi\u2011\
  Fi attack hunters, TV\u2011B\u2011Gone IR control, Wi\u2011Fi spam, AppleJuice Bluetooth\
  \ spam, and a captive portal that logs captured credentials."
readme_lang: en
readme_sha: 5bc0b136d8cb00edab16bfb13f598058fb63e384b4f9392ba30ea22481353925
---

# M5Stick NEMO

M5Stick NEMO is a Wi-Fi/BLE/IR pentesting firmware for M5Stack's StickC-family devices.
