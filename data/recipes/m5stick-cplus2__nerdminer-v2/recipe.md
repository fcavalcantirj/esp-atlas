---
id: m5stick-cplus2__nerdminer-v2
type: recipe
board: m5stick-cplus2
firmware: nerdminer-v2
status: unverified
chip_family: esp32
firmware_version: nerdminer-release-V1.8.3
flash:
  method: release-bin
  bin_url: https://github.com/BitMaker-hub/NerdMiner_v2/releases/download/nerdminer-release-V1.8.3/M5Stick-C-Plus2_factory.bin
  offset: '0x0'
sources:
- field: 'flash.bin_url'
  url: https://github.com/BitMaker-hub/NerdMiner_v2/releases/tag/nerdminer-release-V1.8.3
  verified: '2026-08-26'
- field: '*'
  url: https://github.com/BitMaker-hub/NerdMiner_v2
  verified: '2026-08-26'
---

# m5stick-cplus2 x nerdminer-v2

Release `nerdminer-release-V1.8.3` ships a dedicated `M5Stick-C-Plus2_factory.bin` merged
image (bootloader + partitions + app, flashable at `0x0`).
