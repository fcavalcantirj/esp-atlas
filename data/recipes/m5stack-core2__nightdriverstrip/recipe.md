---
id: m5stack-core2__nightdriverstrip
type: recipe
board: m5stack-core2
firmware: nightdriverstrip
status: unverified
chip_family: esp32
notes: "Board-specific evidence: NightDriverStrip's platformio.ini defines env:m5stackdemo, which extends the dev_m5stack section: board = m5stack-core2, build flag -DM5STACKCORE2=1, M5Unified, PSRAM flags and an 8 MB partition table (commit 971c066). Build that environment; it is the M5Stack demo build, so attach your LED strip to the data pin the project configures for M5STACKCORE2 (the README notes pin 32 for this board). Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip
  verified: '2026-11-06'
- field: 'board'
  url: https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/971c066b37dbe3dbb9ac1096d9e72f32ab5b3452/platformio.ini
  verified: '2026-11-06'
---

NightDriverStrip on the M5Stack Core2 (ESP32). `unverified`.

The project ships an `m5stackdemo` PlatformIO environment built for the Core2
(`board = m5stack-core2`, `-DM5STACKCORE2=1`). That is source evidence of intended
support, not proof that today's code builds or runs: no current successful build
has been confirmed, and it has not been tested on hardware for this atlas.
