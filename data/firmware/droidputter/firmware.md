---
id: droidputter
type: firmware
name: droidputter
url: https://github.com/fcavalcantirj/droidputer
category: multi
maintainer: fcavalcantirj
capabilities:
- gps
popularity:
  stars: 58
  forks: 7
  as_of: '2026-11-07'
  github_repo_id: 1354773174
  github_as_of: '2026-11-07T13:05:00Z'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-09-20'
- field: popularity
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-09-20'
- field: summary
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-10-06'
- field: popularity.forks
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-11-07'
- field: popularity.github_as_of
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-11-07'
- field: popularity.github_repo_id
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-11-07'
- field: popularity.stars
  url: https://github.com/fcavalcantirj/droidputer
  verified: '2026-11-07'
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

Install it from [Google Play](https://play.google.com/store/apps/details?id=com.droidputter). Project site and public stats: [droidputer.vercel.app](https://droidputer.vercel.app).
