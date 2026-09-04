---
id: esp32-s3-devkitc-1__ruview
type: recipe
board: esp32-s3-devkitc-1
firmware: ruview
status: unverified
chip_family: esp32-s3
firmware_version: v0.8.8-esp32
notes: "RuView's own README names this board twice: \"Recommended boards | ESP32-S3-DevKitC-1, XIAO ESP32-S3\", and a dedicated build note for \"Display-less boards (ESP32-S3-DevKitC-1 and similar)\" telling you to build with the `sdkconfig.defaults.devkitc` overlay, because the default build compiles display support in and its runtime panel probe false-positives on a board with no panel — which disables the MGMT+DATA CSI upgrade and collapses CSI yield to 0 pps. This board record carries 4 MB of flash, so the matching prebuilt package is `esp32-csi-node-v0.8.8-s3-4mb-flash-bundle.zip`; the `s3-8mb` bundle is for 8 MB S3 boards. No `flash` block is declared on purpose: the bundle is a four-file install (bootloader 0x0, partition-table 0x8000, otadata 0xf000, app 0x20000) and the bare `esp32-csi-node-v0.8.8-s3-4mb.bin` asset is the application image only, so it cannot be flashed at 0x0 as a single merged binary and must not be offered as a one-click in-browser flash. `unverified`: not yet run on real hardware here."
sources:
- field: '*'
  url: https://github.com/ruvnet/RuView/blob/main/firmware/esp32-csi-node/README.md
  verified: '2026-09-04'
- field: 'board'
  url: https://github.com/ruvnet/RuView/blob/main/firmware/esp32-csi-node/sdkconfig.defaults.devkitc
  verified: '2026-09-04'
- field: 'firmware_version'
  url: https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32
  verified: '2026-09-04'
---

# esp32-s3-devkitc-1 x ruview

RuView names the ESP32-S3-DevKitC-1 as a recommended board for its CSI node, and
ships a build overlay specifically for it.

**Build with the devkitc overlay.** This is a display-less board. RuView's
default build compiles display support in, and its runtime panel probe
false-positives when there is no panel — which turns off the MGMT+DATA CSI
upgrade and drops CSI yield to zero. Use `sdkconfig.defaults.devkitc`.

**Take the 4 MB bundle.** This board has 4 MB of flash, so the matching package
from the `v0.8.8-esp32` release is `esp32-csi-node-v0.8.8-s3-4mb-flash-bundle.zip`.

**Flashing is four files, not one.** Extract the bundle and write each part at
its own offset:

```bash
python -m esptool --chip esp32s3 --port /dev/ttyACM0 --baud 460800 \
  write_flash --flash_mode dio --flash_size 4MB \
  0x0     bootloader.bin \
  0x8000  partition-table.bin \
  0xf000  ota_data_initial.bin \
  0x20000 esp32-csi-node.bin
```

The standalone `esp32-csi-node-v0.8.8-s3-4mb.bin` asset is the application image
on its own. RuView's README says writing only `0x20000` is safe just for a node
that is already provisioned and reports `running_partition` as `ota_0` — so it is
an update path, not a first install.

`unverified` — nobody has run this on the hardware yet.
