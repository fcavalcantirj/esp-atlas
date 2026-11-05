---
id: lilygo-t-deck__icenav-v3
type: recipe
board: lilygo-t-deck
firmware: icenav-v3
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: IceNav-v3's README lists the ordinary LilyGO T-Deck as a supported device, separately from the T-Deck Plus, and its platformio.ini defines a dedicated build environment env:TDECK_ESP32S3 (both pinned at commit 69e82f7). Not verified: no current successful T-Deck build was confirmed (the project's Nov 4 scheduled CI run skipped the T-Deck step after another target failed; the last passing TDECK_ESP32S3 job found was Oct 6), and nobody has flashed it on hardware for this atlas. Build it from the TDECK_ESP32S3 environment; this is not a T-Deck Plus recipe."
sources:
- field: '*'
  url: https://github.com/jgauchia/IceNav-v3
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/jgauchia/IceNav-v3/blob/69e82f7c5d5e4d0fbcf164b394fa048978a06954/README.md
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/jgauchia/IceNav-v3/blob/69e82f7c5d5e4d0fbcf164b394fa048978a06954/platformio.ini
  verified: '2026-11-05'
---

IceNav-v3 on the LilyGO T-Deck (ESP32-S3). `unverified`.

The project names the ordinary T-Deck as a supported device (distinct from the
T-Deck Plus) and ships a dedicated `TDECK_ESP32S3` PlatformIO environment for it.
That is source evidence of intended support, not proof that today's code builds or
runs: no current successful T-Deck build has been confirmed, and it has not been
tested on hardware for this atlas.
