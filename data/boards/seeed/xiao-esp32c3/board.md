---
id: xiao-esp32c3
type: board
brand: seeed
name: Seeed Studio XIAO ESP32C3
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: xiao
price_tier: cheap
dimensions_mm:
- 21
- 17.8
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
extras:
- external-antenna-ipex
io:
  gpio_exposed: 11
  gpio_free: 8
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 4 MB flash, no PSRAM
- U.FL external antenna included
- onboard Li-ion charge management + charge LED
- 'io.gpio_exposed=11 QUOTED: vendor Specifications table states "11x GPIO(PWM)"'
- 'io.gpio_free=8 DERIVED, not quoted (SPEC-io-power.md §5.3). Pin Map table breaks
  out D0-D10 = 11 pads total (quoted: D0=GPIO2, D1=GPIO3, D2=GPIO4, D3=GPIO5, D4=GPIO6,
  D5=GPIO7, D6=GPIO21, D7=GPIO20, D8=GPIO8, D9=GPIO9, D10=GPIO10). Subtracting esp32-c3''s
  soc.reserved_pins that are exposed -- strapping {2,8,9} (3, all exposed) and usb_flash_tied
  {18,19} (0 exposed) -- gives 11 - 3 - 0 = 8. Math not vendor-stated; verify before
  treating as exact.'
- 'io.power_out QUOTED: vendor Specifications table states "Max 3.3V Output Current:
  500mA" (Power(Typ.) row, Test Condition: BAT Pin Input @ 3.8V, Source Capability:
  3A). Note: the page''s separate "Power Pins" narrative section states a conflicting
  "You can draw 700mA" for the 3V3 pin (likely reused boilerplate across the XIAO
  line); the formal spec-table figure is used here as the board-specific value.'
sources:
- field: '*'
  url: https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/
  verified: '2026-08-21'
- field: io.gpio_exposed
  url: https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/
  verified: '2026-08-26'
- field: io.power_out
  url: https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/
  verified: '2026-08-26'
---

# Seeed Studio XIAO ESP32C3

Thumb-sized bare-C3 XIAO board: 4 MB flash, USB-C, onboard LiPo charging, U.FL external antenna.
