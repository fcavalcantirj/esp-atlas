---
id: esp32-c6-devkitc-1__ruview
type: recipe
board: esp32-c6-devkitc-1
firmware: ruview
status: unverified
chip_family: esp32-c6
firmware_version: v0.8.8-esp32
notes: "The firmware's C6 support is first-party and well cited: `sdkconfig.defaults.esp32c6` sets `CONFIG_IDF_TARGET=\"esp32c6\"` with `CONFIG_ESPTOOLPY_FLASHSIZE=\"4MB\"`, the `v0.8.8-esp32` release ships `esp32-csi-node-v0.8.8-c6-4mb-flash-bundle.zip` (\"Fresh ESP32-C6 installation using the supported 4 MB layout\"), and the README calls the C6 its research target. What is NOT cited upstream is this exact board. RuView's root README hardware table lists its \"ESP32-C6 research node\" against a generic \"ESP32-C6-DevKit ($6-10)\", and its transport test notes say only \"Two ESP32-C6 boards\" — no model number anywhere. That generic name is ambiguous between the two C6 devkits this atlas catalogues, `esp32-c6-devkitc-1` and `esp32-c6-devkitm-1`; the DevKitC-1 is the fuller reference board and the likelier reading, but picking it is our inference, which is why the recipe stays `unverified`. Note also that this board record carries 8 MB of flash while RuView ships only a 4 MB C6 layout; the 4 MB bundle boots on an 8 MB part, it simply does not use the extra flash. No `flash` block is declared: the bundle is a four-file install (bootloader 0x0, partition-table 0x8000, otadata 0xf000, app 0x20000) and the bare `.bin` asset is the application image alone."
sources:
- field: '*'
  url: https://github.com/ruvnet/RuView/blob/main/firmware/esp32-csi-node/sdkconfig.defaults.esp32c6
  verified: '2026-09-04'
- field: 'firmware_version'
  url: https://github.com/ruvnet/RuView/releases/tag/v0.8.8-esp32
  verified: '2026-09-04'
- field: 'chip_family'
  url: https://github.com/ruvnet/RuView/blob/main/firmware/esp32-csi-node/README.md
  verified: '2026-09-04'
---

# esp32-c6-devkitc-1 x ruview

RuView builds for the ESP32-C6 — `sdkconfig.defaults.esp32c6` sets
`CONFIG_IDF_TARGET="esp32c6"`, and the `v0.8.8-esp32` release ships
`esp32-csi-node-v0.8.8-c6-4mb-flash-bundle.zip`, described upstream as a "Fresh
ESP32-C6 installation using the supported 4 MB layout". The README calls the C6
the project's research target, for Wi-Fi 6 / 802.15.4 / TWT work.

**Which C6 board is our inference, not RuView's claim.** RuView's hardware table
lists its C6 research node against a generic "ESP32-C6-DevKit ($6–10)", and its
test notes say only "Two ESP32-C6 boards" — no model number. This atlas
catalogues two boards that answer to that name, `esp32-c6-devkitc-1` and
`esp32-c6-devkitm-1`. The DevKitC-1 is the fuller reference board and the likelier
reading, but nobody upstream said so, which is why this recipe is `unverified`.

**Use the C6 bundle, and only the C6 bundle.** RuView's README is explicit:
never flash an S3 bundle onto a C6, or a C6 bundle onto an S3. This board carries
8 MB of flash and RuView publishes only a 4 MB C6 layout; that image boots fine,
it just leaves the upper flash unused.

```bash
python -m esptool --chip esp32c6 --port /dev/ttyACM0 --baud 460800 \
  write_flash --flash_mode dio --flash_size 4MB \
  0x0     bootloader.bin \
  0x8000  partition-table.bin \
  0xf000  ota_data_initial.bin \
  0x20000 esp32-csi-node.bin
```

`unverified` — not run on the hardware here, and the board pairing is reasoned
rather than cited.
