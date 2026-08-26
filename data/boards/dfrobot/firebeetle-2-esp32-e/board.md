---
id: firebeetle-2-esp32-e
type: board
brand: dfrobot
name: DFRobot FireBeetle 2 ESP32-E
soc: esp32
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
extras:
- rgb-led
- sd-card
io:
  gpio_free: 12
notes:
- 4 MB flash
- ESP32-WROOM-32E module, 520 KB SRAM
- PH2.0 connector for 3.7 V Li-ion, onboard charging circuit
- GDI display connector onboard
- DFRobot sells a separate "FireBeetle 2 ESP32-E (N16R2)" SKU (DFR1139) specifically to add PSRAM, confirming this base DFR0654 board (whose own spec page never mentions PSRAM) uses the non-R2 ESP32-WROOM-32E ordering code with no PSRAM
- 'io.gpio_free=12 DERIVED, not quoted (SPEC-io-power.md §5.3). The page''s stated
  totals conflict ("up to 24 physical GPIOs" vs "Digital Pins x18"), so gpio_exposed
  is left unquoted; instead the board''s own GPIO pin table is used directly. That
  table enumerates 20 exposed pads (quoted from the wiki GPIO table): GPIO 0,1,2,3,4,12,13,14,15,18,19,21,22,23,25,26,34,35,36,39.
  Subtracting esp32''s soc.reserved_pins that are exposed -- strapping {0,2,12,15}
  exposed of {0,2,5,12,15} (4; GPIO5 is not broken out), input_only {34,35,36,39}
  (4, all exposed), and usb_flash_tied {6,7,8,9,10,11} (0 exposed) -- gives 20 -
  4 - 4 - 0 = 12. Math not vendor-stated; verify before treating as exact.'
sources:
- field: '*'
  url: https://wiki.dfrobot.com/dfr0654/
  verified: '2026-08-22'
- field: psram_mb
  url: https://wiki.dfrobot.com/dfr1139/
  verified: '2026-08-24'
- field: io.gpio_free
  url: https://wiki.dfrobot.com/dfr0654/
  verified: '2026-08-26'
---

# DFRobot FireBeetle 2 ESP32-E

Low-power IoT main board on the ESP-WROOM-32E module: 4 MB flash, USB-C, onboard Li-ion charging via PH2.0 connector, WS2812 RGB LED, and a microSD slot.
