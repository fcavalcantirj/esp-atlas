---
id: adafruit-feather-esp32-s3-reverse-tft
type: board
brand: adafruit
name: Adafruit ESP32-S3 Reverse TFT Feather (4MB Flash 2MB PSRAM)
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: feather
price_tier: medium
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 1.14in 240x135 IPS ST7789
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 23
  gpio_free: 18
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 4 MB flash, 2 MB PSRAM, 512 KB SRAM
- Display mounted on the reverse side of the board
- LiPoly battery with built-in USB-C charging; MAX17048 I2C battery monitor
- Three user tactile buttons (D0, D1, D2); STEMMA QT connector with switchable power
- Dimensions not specified on the product page (omitted)
- 'io.power_out QUOTED: vendor page states "3.3V - These pins are the output from
  the 3.3V regulator, they can supply 500mA peak."'
- 'io.gpio_exposed=23 QUOTED: vendor pinouts page lists broken-out header pads D5,
  D6, D9, D10, D11, D12, D13 (7 digital), A0-A5 (6 analog, dual-named D8/D14-D18),
  SCK/MOSI/MISO (SPI), RX/TX (UART), SCL/SDA (I2C) = 20, plus the three user
  button pins D0/D1/D2 which the vendor page confirms are also header-broken-out
  = 23 GPIO-capable pads. io.gpio_free=18 DERIVED: cross-referencing the vendor
  firmware repo''s own CircuitPython board pin-definition (pins.c) maps every
  header pad to a GPIO -- of esp32-s3''s soc.reserved_pins, GPIO0 (D0/BOOT,
  strapping), GPIO3 (SDA, strapping), and GPIO35/36/37 (MOSI/SCK/MISO,
  usb_flash_tied) are exposed pads (5 total); the onboard TFT is wired to
  dedicated non-header pins GPIO40/41/42/45 (TFT_DC/RESET/CS/BACKLIGHT) and
  NeoPixel to GPIO7/21/33, none of which count against the header -- so
  23 - 5 = 18'
sources:
- field: '*'
  url: https://www.adafruit.com/product/5691
  verified: '2026-08-22'
- field: io.power_out
  url: https://learn.adafruit.com/esp32-s3-reverse-tft-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/esp32-s3-reverse-tft-feather/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/adafruit/circuitpython/blob/main/ports/espressif/boards/adafruit_feather_esp32s3_reverse_tft/pins.c
  verified: '2026-08-26'
---

# Adafruit ESP32-S3 Reverse TFT Feather

Feather-form ESP32-S3 board with a reverse-mounted 1.14in 240x135 IPS display, native USB-C, LiPoly charging, and STEMMA QT.
