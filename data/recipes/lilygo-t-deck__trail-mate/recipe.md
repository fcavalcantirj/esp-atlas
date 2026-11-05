---
id: lilygo-t-deck__trail-mate
type: recipe
board: lilygo-t-deck
firmware: trail-mate
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: trail-mate's README support table lists the LILYGO T-Deck as a primary validation target with its own tdeck environment, separate from the T-Deck Pro, and the repository has a dedicated variants/tdeck/envs/tdeck.ini and boards/tdeck (commit 4732374). Build the tdeck environment; the default environment targets the T-LoRa-Pager. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/vicliu624/trail-mate
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/vicliu624/trail-mate/blob/4732374d0457429db16bb8d70e02dcfdf4a9ca89/README.md
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/vicliu624/trail-mate/blob/4732374d0457429db16bb8d70e02dcfdf4a9ca89/variants/tdeck/envs/tdeck.ini
  verified: '2026-11-05'
---

trail-mate on the LilyGO T-Deck (ESP32-S3). `unverified`.

The project lists the T-Deck as a primary validation target and ships a dedicated
`tdeck` PlatformIO environment (not the default, which targets the T-LoRa-Pager).
That is source evidence of intended support, not proof that today's code builds or
runs: no current successful build has been confirmed, and it has not been tested on
hardware for this atlas.
