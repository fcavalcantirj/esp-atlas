---
id: lilygo-t-dongle-s3
type: board
brand: lilygo
name: T-Dongle-S3
soc: esp32-s3
flash_mb: 16
psram_mb: 0
form_factor: t-dongle
price_tier: cheap
display: 0.96in 80x160 ST7735 IPS
io:
  gpio_free: 2
notes:
- ESP32-S3 Xtensa LX7; 16 MB flash
- Wi-Fi 802.11 b/g/n, Bluetooth 5
- Available in LCD/no-LCD and internal/external-antenna variants
- LilyGO's official spec table for T-Dongle-S3 explicitly lists "No PSRAM"
- 'io.gpio_free=2 DERIVED, not quoted (SPEC-io-power.md §5.3). The vendor Pin Diagram
  table lists RGB DIN=GPIO40, RGB CLK=GPIO39, SDMMC D0-D3/CLK/CMD=GPIO14/17/21/18/12/16,
  Button=GPIO0, QWIIC TX=GPIO43, QWIIC RX=GPIO44 -- of these, only the QWIIC connector
  (TX/RX) is externally accessible; the RGB LED, SD slot, and button rows are internal-only.
  So the board''s exposed-pad set is {43,44} (2 pads). Subtracting esp32-s3''s soc.reserved_pins
  that are exposed -- neither 43 nor 44 is in strapping {0,3,45,46} or usb_flash_tied
  {19,20,35,36,37} -- gives 2 - 0 = 2. Math not vendor-stated; verify before treating
  as exact.'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-dongle-s3
  verified: '2026-08-22'
- field: psram_mb
  url: https://github.com/Xinyuan-LilyGO/T-Dongle-S3/blob/master/docs/en/t-dongle-s3/REAMDE.MD
  verified: '2026-08-24'
- field: io.gpio_free
  url: https://wiki.lilygo.cc/products/t-dongle-series/t-dongle-s3/
  verified: '2026-08-26'
---

# T-Dongle-S3

Compact ESP32-S3 dongle-form board with a 0.96in ST7735 IPS display and 16 MB flash.
