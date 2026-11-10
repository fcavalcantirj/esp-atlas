---
id: m5stick-s3__squachwatch-cyd
type: recipe
board: m5stick-s3
firmware: squachwatch-cyd
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: SquachWatch-CYD's platformio.ini defines env:sticks3 (build flag -DSTICKS3=1, 8 MB flash, OPI PSRAM, USB CDC on boot, its own TFT setup header include/sticks3_user_setup.h), and the README Boards table lists M5Stack StickS3 as BETA with a web-flasher manifest (web-flasher/manifest-sticks3.json), all at commit bd84f6a. Flash it from the project's web flasher or build with `pio run -e sticks3 -t upload`. The StickS3 build is upstream BETA; the project's primary target is the ESP32-2432S028R Cheap Yellow Display. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/skizzophrenic/SquachWatch-CYD
  verified: '2026-11-06'
- field: 'board'
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/bd84f6a353039582ae11da72f7876288b7bed873/platformio.ini
  verified: '2026-11-06'
- field: 'notes'
  url: https://github.com/skizzophrenic/SquachWatch-CYD/blob/bd84f6a353039582ae11da72f7876288b7bed873/README.md
  verified: '2026-11-06'
---

SquachWatch-CYD on the M5StickS3 (ESP32-S3). `unverified`; upstream ships a dedicated BETA `sticks3` build.
