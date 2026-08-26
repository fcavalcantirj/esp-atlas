---
id: lolin-d32-pro
type: board
brand: lolin
name: LOLIN D32 Pro
soc: esp32
psram_mb: 4
form_factor: devkit
price_tier: cheap
dimensions_mm:
- 65
- 25.4
usb:
  bridge: ch340
power:
  battery_connector: true
  charging: true
extras:
- sd-card
io:
  gpio_exposed: 22
notes:
- ESP32 Wi-Fi + Bluetooth chip; 16 MB or 4 MB flash (variant-dependent), 4 MB PSRAM
- TF (Micro SD) card slot, SPI mode
- Onboard LOLIN I2C port and LOLIN TFT port headers
- Lithium battery interface, PH-2.0 2-pin connector, 500 mA max charging current,
  supports 3.7 V LiPo
- Built-in LED on GPIO5
- Physical USB connector shape not stated on the official page (omitted)
- 'Weight: 7.5 g'
- 'io.gpio_exposed=22 QUOTED: vendor page Technical specs table states "Digital
  I/O Pins | 22"; no enumerated GPIO pin-list/table is published (only partial
  Analog Input/Output pin numbers and LED_BUILTIN=GPIO5), so gpio_free is omitted.
  The 500 mA figure on this page is LiPo charging current, not a GPIO/rail output
  rating, so power_out is omitted'
sources:
- field: '*'
  url: https://www.wemos.cc/en/latest/d32/d32_pro.html
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://www.wemos.cc/en/latest/d32/d32_pro.html
  verified: '2026-08-26'
---

# LOLIN D32 Pro

ESP32 devkit with 16 MB flash (4 MB variant), 4 MB PSRAM, Micro SD slot, LOLIN I2C/TFT ports, LiPo battery/charging interface, CH340 USB-UART bridge.
