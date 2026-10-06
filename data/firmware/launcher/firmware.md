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
- esp32-c3
- esp32-c5
- esp32-c6
- esp32-p4
- esp32-s2
- esp32-s3
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
  stars: 2139
  forks: 257
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-08-23'
- field: popularity
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-09-01'
- field: socs
  url: https://github.com/bmorcelli/Launcher/blob/main/boards/waveshare-esp32-s3-lcd-147/platformio.ini#L53
  verified: '2026-09-10'
- field: summary
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-10-06'
summary: "Launcher is a firmware application for ESP32\u2011based devices (such as\
  \ M5Stack, Lilygo, SeeedStudio, Waveshare, CYD, Marauder, etc.) that offers a menu\u2011\
  driven interface to install and manage other binaries via OTA, SD card, or a Web\
  \ UI, plus file management, configuration, and partition\u2011management tools."
readme_lang: en
readme_sha: c86ec30a06862b3811f97fe0eb1f629abbcb1b715d8b7d13113fb4b66463ab3e
---

# Launcher

Launcher is a firmware app-store/loader spanning dozens of ESP32-family boards, federating device catalogs from projects and M5Burner.
