---
id: firebeetle-2-esp32-s3
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: firebeetle
price_tier: medium
dimensions_mm:
- 25.4
- 60
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- camera
io:
  gpio_exposed: 26
  gpio_free: 18
notes:
- 16 MB flash, 8 MB PSRAM (ESP32-S3-WROOM-1-N16R8)
- Onboard OV2640 camera (2 MP, 68° FOV) with independent power circuit
- GDI display connector onboard
- ETA6003 Li-ion charge management, max 1 A
- 'io.gpio_exposed=26 QUOTED: vendor page states "Digital I/O x26"'
- 'io.gpio_free=18 DERIVED (SPEC-io-power.md §5.3): the 26 exposed GPIOs are identified
  from the official schematic netlist (P3/P4 headers plus the GDI FPC connector,
  which shares many of the same nets): {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,38,43,44,47}
  -- 26 unique GPIOs, matching the vendor count exactly. Subtracting esp32-s3''s
  soc.reserved_pins that are exposed -- strapping {0,3}: both present (45,46 are
  camera-only, not header-exposed); usb_flash_tied {19,20}: both present on the
  header despite also routing to the native-USB Type-C lines (35,36,37 are camera-only)
  -- removes 4. The onboard OV2640 camera''s parallel (DVP) interface permanently
  consumes GPIO4/5/6/8 (DVP_Y5/PCLK/VSYNC/Y7) even though those same pins are also
  broken out on the header, removing another 4. 26 - 4 - 4 = 18. Math not vendor-stated;
  verify before treating as exact.'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0975
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr0975
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://dfimg.dfrobot.com/wiki/20529/DFR0975_firebeetle-esp32-s3-ai-acceleration-board_schematics_V1.0.pdf
  verified: '2026-08-26'
---

# DFRobot FireBeetle 2 ESP32-S3

AI-oriented ESP32-S3 board with 16 MB flash, 8 MB PSRAM, an onboard OV2640 camera, USB-C, and a GDI display connector for AIoT and image-recognition projects.
