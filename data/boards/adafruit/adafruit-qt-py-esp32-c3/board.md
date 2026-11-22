---
id: adafruit-qt-py-esp32-c3
type: board
brand: adafruit
name: Adafruit QT Py ESP32-C3 WiFi Dev Board with STEMMA QT
soc: esp32-c3
flash_mb: 4
psram_mb: 0
form_factor: qt-py
price_tier: cheap
dimensions_mm:
- 22.0
- 17.8
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: false
extras:
- rgb-led
- stemma-qt
io:
  gpio_exposed: 11
  gpio_free: 10
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 500
notes:
- 4 MB flash
- USB-to-serial handled by the ESP32-C3's own USB-Serial/JTAG peripheral, not native
  USB device mode (cannot act as keyboard/disk)
- Battery input pads on underside with diode protection for external packs up to 6V;
  no onboard charging circuit
- ESP32-C3 has no PSRAM interface at all (chip datasheet lists no PSRAM/external-RAM
  support)
- 'io.gpio_exposed=11 QUOTED: vendor page states "There are eleven GPIO pins broken
  out to pads."'
- io.gpio_free=10 DERIVED, not quoted (SPEC-io-power.md §5.3). Pinouts page gives
  explicit GPIO numbers for all 11 broken-out pads (A0=GPIO4, A1=GPIO3, A2=GPIO1,
  A3=GPIO0, SDA=GPIO5, SCL=GPIO6, RX=GPIO20, TX=GPIO21, SCK=GPIO10, MI=GPIO8, MO=GPIO7).
  Subtracting esp32-c3's soc.reserved_pins that are exposed among those 11 -- strapping
  {8} (1) -- gives 11 - 1 = 10. Math not vendor-stated; verify before treating as
  exact.
- 'io.power_out QUOTED: vendor page states "These pins are the output from the 3.3V
  regulator, they can supply 500mA peak."'
usb_serial: native-usb-serial-jtag
getting_started: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board
images:
  photo: https://cdn-learn.adafruit.com/guides/images/000/003/547/medium800/Screenshot_1.png
  pinout: https://cdn-learn.adafruit.com/assets/assets/000/129/455/medium800/adafruit_products_stemma-circuit.png?1713883230
platformio_definitions:
- id: adafruit_qtpy_esp32c3
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: 345d38e36e91cc58ef11b8227142bd862c3796bd8ea9bfbcecc347fbe744f137
- id: adafruit_qtpy_esp32c3
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 54e9b1c861805175fb3ac4a121ba3ce403b3f78062d492c90905dddceefca4d6
sources:
- field: '*'
  url: https://www.adafruit.com/product/5405
  verified: '2026-08-22'
- field: psram_mb
  url: https://documentation.espressif.com/esp32-c3_datasheet_en.html
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board/pinouts
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board/pinouts
  verified: '2026-08-26'
- field: io.power_out
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board/pinouts
  verified: '2026-08-26'
- field: usb_serial
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board
  verified: '2026-09-13'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board
  verified: '2026-09-13'
- field: images
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board
  verified: '2026-09-13'
- field: images.pinout
  url: https://cdn-learn.adafruit.com/assets/assets/000/129/455/medium800/adafruit_products_stemma-circuit.png?1713883230
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/adafruit_qtpy_esp32c3.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/adafruit_qtpy_esp32c3.json
  verified: '2026-11-22'
---

# Adafruit QT Py ESP32-C3

Tiny ESP32-C3 board with USB-C, STEMMA QT, RGB NeoPixel, and 4 MB flash.
