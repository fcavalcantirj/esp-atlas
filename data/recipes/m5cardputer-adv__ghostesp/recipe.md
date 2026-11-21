---
id: m5cardputer-adv__ghostesp
type: recipe
board: m5cardputer-adv
firmware: ghostesp
status: unverified
chip_family: esp32-s3
notes: "ghostesp names this board as Cardputer ADV in its CI matrix; derived from the repo's own build files, not verified on hardware. Evidence check v3 PASS — named: the source names m5cardputer-adv."
sources:
- field: '*'
  url: https://github.com/GhostESP-Revival/GhostESP
  verified: '2026-11-18'
- field: board
  url: https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
  verified: '2026-11-18'
---

# m5cardputer-adv x ghostesp

`ghostesp` declares `Cardputer ADV` in its CI matrix; that name resolves to the catalogued board `m5cardputer-adv` (esp32-s3). Status `unverified` until someone with the hardware confirms it.

- rank 3 ci: `Cardputer ADV` — https://github.com/GhostESP-Revival/GhostESP/blob/Development-deki/.github/workflows/compile_all.yml
