---
id: lilygo-t-display-s3__launcher
type: recipe
board: lilygo-t-display-s3
firmware: launcher
status: known-good
chip_family: esp32-s3
flash:
  method: web-flasher
sources:
- field: 'notes'
  url: https://github.com/bmorcelli/Launcher/wiki/Supported-devices
  verified: '2026-08-24'
- field: '*'
  url: https://github.com/bmorcelli/Launcher/wiki/Supported-devices
  verified: '2026-08-23'
---

# lilygo-t-display-s3 x launcher

No `flash.bin_url`: the Supported-devices wiki lists T-Display-S3 ("Touch and no
touch") as supported since 2.2.1, but release 2.8.0 ships only `-touch`, `-pro`
and `-amoled` variants with no plain T-Display-S3 asset, so which build serves
the non-touch board is unresolved. Flashing stays a guided handoff until it is.

Launcher runs on the LilyGo T-Display-S3, per its official Supported-devices list.
