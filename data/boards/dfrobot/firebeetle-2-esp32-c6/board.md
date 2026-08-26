---
id: firebeetle-2-esp32-c6
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-C6
soc: esp32-c6
flash_mb: 4
psram_mb: 0
form_factor: firebeetle
price_tier: cheap
dimensions_mm:
- 25.4
- 60
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
io:
  gpio_exposed: 19
  gpio_free: 16
notes:
- 4 MB flash
- Supports 5 V solar panel charging via CN3165 MPPT chip, max 0.5 A
- GDI display connector onboard
- ESP32-C6 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM support)
- 'io.gpio_exposed=19 QUOTED: vendor page states "Digital I/O: x19"'
- 'io.gpio_free=16 DERIVED (SPEC-io-power.md §5.3): the vendor page has no text
  pin table, so the 19 exposed GPIOs are identified from the official schematic
  netlist (P1/P2 headers plus the GDI FPC connector, which shares the same nets):
  {1,2,3,4,5,6,7,8,9,14,15,16,17,18,19,20,21,22,23} -- 19 unique GPIOs, matching
  the vendor count exactly. Subtracting esp32-c6''s soc.reserved_pins that are exposed
  -- strapping {8,9,15}: all 3 present; usb_flash_tied {12,13}: 0 present (native
  USB pins are not broken out) -- gives 19 - 3 = 16. GDI-shared pins (IO14/IO15,
  display backlight/reset) are not additionally subtracted since GDI is an optional
  plug-in connector, not a permanently populated display. Math not vendor-stated;
  verify before treating as exact.'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr1075/
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c6_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://wiki.dfrobot.com/dfr1075/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://dfimg.dfrobot.com/wiki/20576/DFR1075_firebeetle-esp32-c6-microcontroller_schematics_v1.zip
  verified: '2026-08-26'
---

# DFRobot FireBeetle 2 ESP32-C6

Low-power ESP32-C6 IoT board for smart-home control: 4 MB flash, USB-C, Li-ion charging plus 5 V solar/MPPT input, and a GDI display connector.
