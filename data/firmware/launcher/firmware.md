---
id: launcher
type: firmware
name: Launcher
url: https://github.com/bmorcelli/Launcher
category: multi
maintainer: bmorcelli
license: MIT
socs:
- esp32
- esp32-s2
- esp32-s3
- esp32-c3
- esp32-c6
- esp32-p4
distribution:
- web-flasher
- releases
capabilities:
- ota
- firmware-store
requires:
- capability: display
  why: its whole function is an on-device menu to browse and flash firmware; no screen,
    no use
  board_signal: display
not_required:
- capability: psram
- capability: ble
- capability: wifi
  why: radios are irrelevant to the loader itself
popularity:
  stars: 2047
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-09-01'
---

# Launcher

Launcher is a firmware app-store/loader spanning dozens of ESP32-family boards, federating device catalogs from projects and M5Burner.
