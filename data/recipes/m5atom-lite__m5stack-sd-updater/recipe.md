---
id: m5atom-lite__m5stack-sd-updater
type: recipe
board: m5atom-lite
firmware: m5stack-sd-updater
status: unverified
chip_family: esp32
notes: "m5stack-sd-updater names this board as M5Atom in its CI matrix; derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/tobozo/M5Stack-SD-Updater
  verified: '2026-09-09'
- field: board
  url: https://github.com/tobozo/M5Stack-SD-Updater/blob/master/.github/workflows/ArduinoBuild.yml
  verified: '2026-09-09'
---

# m5atom-lite x m5stack-sd-updater

`m5stack-sd-updater` declares `M5Atom` in its CI matrix; that name resolves to the catalogued board `m5atom-lite` (esp32). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `M5Atom` — https://github.com/tobozo/M5Stack-SD-Updater/blob/master/.github/workflows/ArduinoBuild.yml
- rank 3 ci: `m5stack-atom` — https://github.com/tobozo/M5Stack-SD-Updater/blob/master/.github/workflows/ArduinoBuild.yml
