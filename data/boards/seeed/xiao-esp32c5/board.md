---
id: xiao-esp32c5
type: board
brand: seeed
name: Seeed Studio XIAO ESP32C5
aka:
- "seeed_xiao_esp32c5"
soc: esp32-c5
flash_mb: 8
psram_mb: 8
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
  gpio_free: 9
notes:
- 8 MB flash + 8 MB PSRAM
- 'dual-band Wi-Fi 6 (2.4 + 5 GHz): Specifications table states "2.4 GHz & 5 GHz dual-band
  Wi-Fi 6 and Bluetooth 5 (LE)"'
- 'flash_mb/psram_mb QUOTED: Specifications table Memory row states "8 MB PSRAM & 8
  MB Flash"'
- 'dimensions_mm QUOTED: vendor states "As small as a thumb(21x17.8mm)"'
- 'usb.connector=usb-c: vendor states input via "USB Type-C" ("Input voltage (Type-C)"
  on sibling XIAO docs; package "1 x USB Type-C cable") and "Seeed USB Type-C support
  USB 3.1"'
- U.FL external antenna included (Pin Map "U.FL-R-SMT1 ... UFL antenna"; "External RF
  antenna included")
- 'onboard Li-ion charge management + charge LED: Specifications table "Battery Charge
  Chip SGM40567" and "Onboard LEDs Charge / USER LED"; vendor states "Supports lithium
  battery charge and discharge management"'
- 'io.gpio_exposed=11 QUOTED: vendor Specifications table states "PWM/Analog Pins" =
  "11 / 5" (11 PWM-capable pins), matching the Pin Map''s D0-D10 = 11 user pads'
- 'io.gpio_free=9 DERIVED, not quoted (SPEC-io-power.md §5.3). Pin Map table breaks
  out D0-D10 = 11 pads total (quoted: D0=GPIO1, D1=GPIO0, D2=GPIO25, D3=GPIO7, D4=GPIO23,
  D5=GPIO24, D6=GPIO11, D7=GPIO12, D8=GPIO8, D9=GPIO9, D10=GPIO10). Subtracting esp32-c5''s
  soc.reserved_pins that are exposed -- strapping {2,3,7,25,26,27,28} (2 exposed: GPIO25=D2,
  GPIO7=D3) and usb_flash_tied {13,14} (0 exposed) -- gives 11 - 2 - 0 = 9. Math not
  vendor-stated; verify before treating as exact.'
- 'io.power_out OMITTED: the C5 page states no 3V3 output-current figure (no Specifications
  power row and no "you can draw NmA" narrative).'
sources:
- field: '*'
  url: https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/
  verified: '2026-09-11'
- field: io.gpio_exposed
  url: https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/
  verified: '2026-09-11'
- field: io.gpio_free
  url: https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: aka
  url: https://github.com/pioarduino/platform-espressif32/blob/32f6bf400b276b0f61cf42c50490a7808ee3457e/boards/seeed_xiao_esp32c5.json
  verified: '2026-09-11'
---

# Seeed Studio XIAO ESP32C5

Thumb-sized bare-C5 XIAO board: the dual-band Wi-Fi 6 (2.4 + 5 GHz) XIAO, 8 MB flash + 8 MB PSRAM, USB-C, onboard LiPo charging, U.FL external antenna.
