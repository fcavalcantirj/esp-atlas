---
id: lilygo-t-deck__acid-drop
type: recipe
board: lilygo-t-deck
firmware: acid-drop
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: acid-drop's platformio.ini defines a dedicated env:t-deck for the original T-Deck, separate from env:t-deck-plus (commit 51a98f1). The default environment is t-deck-plus; select pio run -e t-deck explicitly for this original-board recipe. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/acidvegas/acid-drop
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/acidvegas/acid-drop/blob/51a98f13d1efd1a9d07333be3957dd60b1ca7cf7/platformio.ini
  verified: '2026-11-05'
---

acid-drop on the LilyGO T-Deck (ESP32-S3). `unverified`.

The project ships a dedicated `t-deck` PlatformIO environment for the original
T-Deck, separate from the `t-deck-plus` one. That is source evidence of intended
support, not proof that today's code builds or runs: no current successful build
has been confirmed, and it has not been tested on hardware for this atlas.
