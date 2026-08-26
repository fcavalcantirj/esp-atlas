---
id: xiao-esp32s3
type: board
brand: seeed
name: Seeed Studio XIAO ESP32S3
soc: esp32-s3
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
  gpio_free: 10
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 700
notes:
- 'ESP32-S3R8: 8 MB flash + 8 MB on-chip PSRAM'
- U.FL external antenna
- onboard LiPo charging
- 'io.gpio_exposed=11 QUOTED: vendor Specifications table (XIAO ESP32-S3 tab) states
  "11x GPIO(PWM)"'
- 'io.gpio_free=10 DERIVED, not quoted (SPEC-io-power.md §5.3). Pin Map table breaks
  out D0-D10 = 11 pads total (quoted: D0=GPIO1, D1=GPIO2, D2=GPIO3, D3=GPIO4, D4=GPIO5,
  D5=GPIO6, D6=GPIO43, D7=GPIO44, D8=GPIO7, D9=GPIO8, D10=GPIO9), matching the vendor''s
  stated "11x GPIO(PWM)" count. (The same table also lists two extra back-side test
  pads D11/D12 = GPIO42/GPIO41, excluded here since they fall outside the vendor''s
  own 11-GPIO count.) Subtracting esp32-s3''s soc.reserved_pins that are exposed --
  strapping {0,3,45,46} (1 exposed: GPIO3=D2) and usb_flash_tied {19,20,35,36,37}
  (0 exposed) -- gives 11 - 1 - 0 = 10. Math not vendor-stated; verify before treating
  as exact.'
- 'io.power_out QUOTED: vendor "Power Pins" section states "3V3 - This is the regulated
  output from the onboard regulator. You can draw 700mA"'
sources:
- field: '*'
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-08-21'
- field: io.gpio_exposed
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-08-26'
- field: io.power_out
  url: https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
  verified: '2026-08-26'
---

# Seeed Studio XIAO ESP32S3

Thumb-sized bare-S3R8 XIAO board: 8 MB flash + 8 MB PSRAM, USB-C, LiPo charging, U.FL antenna.
