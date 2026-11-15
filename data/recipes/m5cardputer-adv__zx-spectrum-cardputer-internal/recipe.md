---
id: m5cardputer-adv__zx-spectrum-cardputer-internal
type: recipe
board: m5cardputer-adv
firmware: zx-spectrum-cardputer-internal
status: unverified
chip_family: esp32-s3
notes: "Board-specific evidence: the repository description names the Cardputer ADV as its target: 'ZX Spectrum 48K emulator for M5Stack Cardputer-Adv with external ILI9488 display support'. Not tested on hardware for this atlas."
sources:
- field: '*'
  url: https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external
  verified: '2026-11-15'
- field: board
  url: https://github.com/AndyAiCardputer/zx-spectrum-cardputer-external
  verified: '2026-11-15'
---

zx-spectrum-cardputer-internal on the M5Stack Cardputer-Adv (ESP32-S3). `unverified`.

The project's own repository description targets the Cardputer ADV. That is source evidence of intended support,
not proof that today's code builds or runs: it has not been tested on hardware for this atlas.
