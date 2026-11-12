---
id: lcdwiki-es3c28p__launcher
type: recipe
board: lcdwiki-es3c28p
firmware: launcher
status: unverified
chip_family: esp32-s3
flash:
  method: release-bin
notes: "launcher names this board as ES3C28P in its release (asset Launcher-ES3C28P.bin) (release 3.0.0); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/bmorcelli/Launcher
  verified: '2026-11-11'
- field: board
  url: https://github.com/bmorcelli/Launcher/releases/tag/3.0.0
  verified: '2026-11-11'
---

# lcdwiki-es3c28p x launcher

`launcher` declares `ES3C28P` in its release; that name resolves to the catalogued board `lcdwiki-es3c28p` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 1 asset: `ES3C28P` — https://github.com/bmorcelli/Launcher/releases/download/3.0.0/Launcher-ES3C28P.bin
