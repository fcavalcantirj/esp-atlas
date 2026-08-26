---
id: adafruit-metro-esp32-s3
type: board
brand: adafruit
name: Adafruit Metro ESP32-S3 (16MB Flash 8MB PSRAM)
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: metro
price_tier: medium
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 25
  gpio_free: 24
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 400
notes:
- 16 MB flash, 8 MB Octal PSRAM, 512 KB SRAM
- LiPoly battery connector with built-in charging; MAX17048 I2C battery monitor
- STEMMA QT connector with switchable power; JTAG 2x5 debug header; Revision B (Nov 2023) fixed NeoPixel/SPI/SD-card pin conflicts with PSRAM
- Dimensions not specified on the product page (omitted)
- 'io.power_out QUOTED: vendor page states "This is the output pin from the 3.3V
  regulator, you can grab up to 400mA from this regulator for accessories, it''s
  also used by the ESP32-S3 which can have spiky current draw."'
- 'io.gpio_exposed=25 QUOTED: vendor pinouts page lists RX/TX (D0/D1), D2-D13 (12
  digital pins), A0-A5 (6 analog), SCL/SDA (I2C), and SCK/MOSI/MISO (ICSP header)
  = 25 GPIO-capable pads. io.gpio_free=24 DERIVED: cross-referencing the vendor
  firmware repo''s own CircuitPython board pin-definition (pins.c) maps every
  header pad to a GPIO -- of esp32-s3''s soc.reserved_pins, only GPIO3 (D3,
  strapping) is exposed; the onboard MicroSD slot shares the same ICSP SCK/MOSI/
  MISO bus (not exclusive) but its SD_CS (GPIO45, itself strapping) is a
  dedicated internal signal with no header pad, and NeoPixel (GPIO46) is
  likewise off-header -- so 25 - 1 = 24'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5500
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-metro-esp32-s3/pinouts
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-metro-esp32-s3/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_metro_esp32s3/pins.c
  verified: '2026-08-26'
---

# Adafruit Metro ESP32-S3

Arduino Uno-form-factor ESP32-S3 board with native USB-C, 16 MB flash / 8 MB PSRAM, LiPoly charging, and STEMMA QT.
