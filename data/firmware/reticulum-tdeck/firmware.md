---
id: reticulum-tdeck
type: firmware
name: T-Deck LXMF Messenger
url: https://github.com/varna9000/reticulum-tdeck
category: mesh
maintainer: varna9000
capabilities:
- lora
- wifi
popularity:
  stars: 37
  forks: 8
  github_as_of: '2026-11-14'
  as_of: '2026-11-14'
socs:
- esp32-s3
distribution:
- releases
sources:
- field: '*'
  url: https://github.com/varna9000/reticulum-tdeck
  verified: '2026-11-14'
- field: capabilities
  url: https://github.com/varna9000/reticulum-tdeck/blob/dd6afceeffd5e86ec3220d7e120b2e2edd1ccb6d/README.md
  verified: '2026-11-14'
- field: socs
  url: https://github.com/varna9000/reticulum-tdeck/blob/dd6afceeffd5e86ec3220d7e120b2e2edd1ccb6d/README.md
  verified: '2026-11-14'
- field: socs
  url: https://github.com/varna9000/reticulum-tdeck/releases/download/v1.15.0/tdeck_firmware.bin
  verified: '2026-11-14'
- field: distribution
  url: https://github.com/varna9000/reticulum-tdeck/releases/tag/v1.15.0
  verified: '2026-11-14'
- field: popularity.github_as_of
  url: https://github.com/varna9000/reticulum-tdeck
  verified: '2026-11-14'
- field: popularity.stars
  url: https://github.com/varna9000/reticulum-tdeck
  verified: '2026-11-14'
- field: popularity.forks
  url: https://github.com/varna9000/reticulum-tdeck
  verified: '2026-11-14'
---

# T-Deck LXMF Messenger

A handheld [Reticulum](https://reticulum.network/) messenger for the LilyGO T-Deck, built on MicroPython.
Releases ship a full 4 MB image (`tdeck_firmware.bin`) for USB flashing or M5Launcher, plus an app-only update image.
A separate T-Deck Pro image exists; this record's recipe covers the original T-Deck.

**Target, derived.** The README states "Board: LilyGO T-Deck v1 (ESP32-S3)" and flashes with
`esptool --chip esp32s3`. The v1.15.0 release image agrees: its ESP image header at 0x0 (magic 0xE9,
4 segments) and the factory app at 0x10000, located through the partition table at 0x8000, both carry
chip_id 9, which esptool maps to ESP32-S3.

Admitted by hand from owner-review question #1703: Jr's release-image gate does not validate merged
flash images (bootloader + partition table + app), so it asked instead of deciding.
