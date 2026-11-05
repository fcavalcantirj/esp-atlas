---
id: lilygo-t-deck__t-deck
type: recipe
board: lilygo-t-deck
firmware: t-deck
status: unverified
chip_family: esp32-s3
notes: "This is LilyGO's own example repository for the T-Deck and T-Deck Plus, not a single application. Its platformio.ini selects env:T-Deck (board=T-Deck) by default and builds one example at a time through src_dir; the default is examples/UnitTest (commit 9aac147). Pick the example you want in src_dir before building. Not verified: no current successful build confirmed and not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/Xinyuan-LilyGO/T-Deck
  verified: '2026-11-05'
- field: 'board'
  url: https://github.com/Xinyuan-LilyGO/T-Deck/blob/9aac147a313975ad063594b3fe11e28a96d94936/platformio.ini
  verified: '2026-11-05'
---

LilyGO's T-Deck example repository on the LilyGO T-Deck (ESP32-S3). `unverified`.

**This is the vendor's collection of example sketches, not one firmware.** The
default `T-Deck` PlatformIO environment builds whichever example `src_dir` points
to, which is `examples/UnitTest` by default. No current successful build has been
confirmed, and it has not been tested on hardware for this atlas.
