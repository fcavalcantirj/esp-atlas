---
id: adafruit-feather-esp32-c6
type: board
brand: adafruit
name: Adafruit ESP32-C6 Feather
aka:
- ADAFRUIT_FEATHER_ESP32C6
soc: esp32-c6
flash_mb: 4
form_factor: feather
price_tier: medium
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
io:
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- '4 MB flash (vendor overview: "4MB of flash")'
- 'psram_mb OMITTED: the vendor page lists flash but does not state any PSRAM, so no
  value is recorded (absence is neutral, not asserted as zero)'
- LiPoly charging and monitoring with the MAX17048; STEMMA QT I2C port; status NeoPixel;
  second low-quiescent LDO (vendor cites as low as 17uA deep sleep)
- 'io.power_out QUOTED: vendor pinouts page states "These pins are the output from
  the 3.3V regulator, they can supply 500mA peak."'
- 'usb_serial derived from usb.bridge (native) + soc usb.type serial-jtag: the ESP32-C6
  flashes over its built-in USB Serial/JTAG core, not a UART bridge. Vendor overview:
  "built in USB Serial core" for debugging only, "cannot run UF2" and cannot act as
  an HID or mass-storage device'
- 'dimensions_mm OMITTED: no board dimensions stated on the vendor overview or pinouts
  pages'
- 'io.gpio_exposed/gpio_free OMITTED: vendor pinouts page does not print an explicit
  broken-out GPIO count, so no count is derived'
getting_started: https://learn.adafruit.com/adafruit-esp32-c6-feather
sources:
- field: '*'
  url: https://www.adafruit.com/product/5933
  verified: '2026-09-11'
- field: '*'
  url: https://learn.adafruit.com/adafruit-esp32-c6-feather/overview
  verified: '2026-09-11'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-esp32-c6-feather/pinouts
  verified: '2026-09-11'
- field: usb_serial
  url: https://learn.adafruit.com/adafruit-esp32-c6-feather/overview
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-esp32-c6-feather
  verified: '2026-09-11'
---

# Adafruit ESP32-C6 Feather

Feather-form ESP32-C6 board (Wi-Fi 6 / BLE 5 / 802.15.4): USB-C with native USB Serial/JTAG, LiPoly JST charging with MAX17048 monitor, NeoPixel, and STEMMA QT.
