---
id: m5stick-s3__doutor-vpd
type: recipe
board: m5stick-s3
firmware: doutor-vpd
status: reported
chip_family: esp32-s3
firmware_version: '0.2.3'
flash:
  method: release-bin
  parts:
  - url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/bootloader.bin
    offset: '0x0'
  - url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/partitions.bin
    offset: '0x8000'
  - url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/boot_app0.bin
    offset: '0xe000'
  - url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/firmware.bin
    offset: '0x10000'
notes: "flash.parts offsets QUOTED from the release's manifest.json `install` list (0, 32768, 57344, 65536). The NVS range and the history partition READ from that release's partitions.bin entries: nvs 0x9000 size 0x5000 (0x9000-0xDFFF), otadata 0xE000, app0 0x10000, history 0x310000 size 0x4E0000."
sources:
- field: '*'
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware
  verified: '2026-10-22'
- field: firmware_version
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/manifest.json
  verified: '2026-10-22'
- field: flash.parts[0].url
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/bootloader.bin
  verified: '2026-10-22'
- field: flash.parts[0].offset
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/manifest.json
  verified: '2026-10-22'
- field: flash.parts[1].url
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/partitions.bin
  verified: '2026-10-22'
- field: flash.parts[1].offset
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/manifest.json
  verified: '2026-10-22'
- field: flash.parts[2].url
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/boot_app0.bin
  verified: '2026-10-22'
- field: flash.parts[2].offset
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/manifest.json
  verified: '2026-10-22'
- field: flash.parts[3].url
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/firmware.bin
  verified: '2026-10-22'
- field: flash.parts[3].offset
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/manifest.json
  verified: '2026-10-22'
- field: notes
  url: https://github.com/fcavalcantirj/doutor-vpd-firmware/releases/download/vpd-gennie-0.2.3-b5-cfa71853c711/partitions.bin
  verified: '2026-10-22'
---

# m5stick-s3 x doutor-vpd

Doutor VPD runs on the M5StickS3 with a Grove ENV III unit; the releases repository names this
board and sensor. Status `reported` until it has been flashed on hardware through esp-atlas.

The release ships four images, and each one is written at its own offset: `bootloader.bin` at
0x0, `partitions.bin` at 0x8000, `boot_app0.bin` at 0xe000 and `firmware.bin` at 0x10000. They
are never merged into one image: the gap between them is the NVS partition (0x9000-0xDFFF in
this release's partition table), and a merged image would fill it with 0xFF. NVS is where the
firmware keeps its saved settings, the stick's hotspot code among them (per the maintainer; the
firmware source is not public).

Leave "erase" unticked in the flasher. The four writes then touch only their own ranges, so the
stick keeps its reading history (the `history` partition at 0x310000) and its hotspot code.
Ticking "erase" wipes the whole flash, history included.
