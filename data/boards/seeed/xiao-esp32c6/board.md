---
id: xiao-esp32c6
type: board
brand: seeed
name: Seeed Studio XIAO ESP32C6
soc: esp32-c6
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
  gpio_free: 11
notes:
- 4 MB flash, no PSRAM
- U.FL external antenna with RF switch on GPIO14
- onboard battery charging
- 'io.gpio_exposed=11 QUOTED: vendor Specifications table states "11x GPIO(PWM)"'
- 'io.gpio_free=11 DERIVED, not quoted (SPEC-io-power.md §5.3). Pin Map table breaks
  out D0-D10 = 11 pads total (quoted: D0=GPIO0, D1=GPIO1, D2=GPIO2, D3=GPIO21, D4=GPIO22,
  D5=GPIO23, D6=GPIO16, D7=GPIO17, D8=GPIO19, D9=GPIO20, D10=GPIO18). Subtracting
  esp32-c6''s soc.reserved_pins that are exposed -- strapping {8,9,10,11,15} (0 exposed)
  and usb_flash_tied {12,13} (0 exposed) -- gives 11 - 0 - 0 = 11 (none of this SoC''s
  reserved pins land on the header). Math not vendor-stated; verify before treating
  as exact.'
- 'io.power_out OMITTED: vendor page has no "Power Pins" section and no stated 5V/3V3
  output-current rating (only input voltage and sleep-mode consumption figures)'
sources:
- field: '*'
  url: https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/
  verified: '2026-08-21'
- field: io.gpio_exposed
  url: https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/
  verified: '2026-08-26'
---

# Seeed Studio XIAO ESP32C6

Thumb-sized bare-C6 XIAO board: Wi-Fi 6 / BLE / 802.15.4, USB-C, LiPo charging, U.FL antenna w/ RF switch.
