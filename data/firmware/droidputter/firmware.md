---
id: droidputter
type: firmware
name: droidputter
url: https://github.com/fcavalcantirj/droidputter
category: multi
maintainer: fcavalcantirj
capabilities:
- gps
popularity:
  stars: 41
  forks: 6
  as_of: '2026-09-20'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/fcavalcantirj/droidputter
  verified: '2026-09-20'
- field: popularity
  url: https://github.com/fcavalcantirj/droidputter
  verified: '2026-09-20'
- field: summary
  url: https://github.com/fcavalcantirj/droidputter
  verified: '2026-10-06'
summary: "Droidputter lets an ESP32\u2011S3 run unmodified Cardputer applications\
  \ while an Android phone provides the display, keyboard, GPS and flashing, by patching\
  \ M5GFX/M5Cardputer to tee pixel writes over the chip's native USB\u2011CDC and\
  \ merge phone input frames. The app builds sources on demand via GitHub Actions,\
  \ flashes the firmware from the phone, and mirrors the ESP32\u2011S3 screen onto\
  \ the phone."
readme_lang: en
readme_sha: d031b88c60323274481f5dd0e3eacb14389d5c9ebcbdd972aef2a97a09bef624
---

Run open-source Cardputer apps on Android: plug an ESP32-S3 over USB-OTG and the phone is the screen, keyboard, GPS and flasher. Apps are rebuilt on demand from GitHub against a display/keyboard shim.
