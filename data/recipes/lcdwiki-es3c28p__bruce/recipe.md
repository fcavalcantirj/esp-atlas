---
id: lcdwiki-es3c28p__bruce
type: recipe
board: lcdwiki-es3c28p
firmware: bruce
status: unverified
chip_family: esp32-s3
flash:
  env: "ES3C28P"
notes: "bruce names this board as ES3C28P in its platformio.ini (env ES3C28P); derived from the repo's own build files, not verified on hardware."
sources:
- field: '*'
  url: https://github.com/BruceDevices/firmware
  verified: '2026-11-11'
- field: flash.env
  url: https://github.com/BruceDevices/firmware/blob/main/boards/ES3C28P/ES3C28P.ini#L17
  verified: '2026-11-11'
- field: board
  url: https://github.com/BruceDevices/firmware/blob/main/boards/ES3C28P/ES3C28P.ini#L17
  verified: '2026-11-11'
---

# lcdwiki-es3c28p x bruce

`bruce` declares `ES3C28P` in its platformio.ini; that name resolves to the catalogued board `lcdwiki-es3c28p` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 2 platformio: `ES3C28P` — https://github.com/BruceDevices/firmware/blob/main/boards/ES3C28P/ES3C28P.ini#L17
