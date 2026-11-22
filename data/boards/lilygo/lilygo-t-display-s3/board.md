---
id: lilygo-t-display-s3
type: board
brand: lilygo
name: T-Display-S3
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: devkit
price_tier: medium
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
power:
  battery_connector: true
  charging: true
display: 1.9in 170x320 IPS ST7789V
io:
  power_out:
    rail_v:
    - 3.3
    rail_ma_max: 100
notes:
- 16 MB flash, 8 MB PSRAM (ESP32-S3R8)
- JST-GH battery connector; STEMMA QT/Qwiic; Touch and non-Touch variants
- 'io.power_out QUOTED: vendor README Electrical Parameters section states "3V pin
  header load does not exceed 100mA" (recorded as the board''s 3.3V logic rail); the
  5V pin header is USB-C passthrough with no fixed rating ("load capacity depends
  on the USB-C adapter"), so only the 3V/100mA figure is recorded'
- 'io.gpio_exposed/gpio_free OMITTED: the official GitHub repo''s pin-definition header
  (examples/factory/pin_config.h) only names the ~25 GPIOs consumed by the onboard
  8080-parallel LCD bus, buttons, battery ADC, touch controller, and optional SD shield;
  it does not enumerate the remaining header-broken-out pins, and neither the product
  page nor README states a total exposed/usable IO count in text (only an un-OCR''d
  pin-diagram image), so left unset per cite-or-omit'
- usb_serial derived from usb.bridge (native) + soc usb.type otg-full-speed + serial-jtag
getting_started: https://lilygo.cc/products/t-display-s3
images:
  photo: https://lilygo.cc/cdn/shop/files/H569_03.jpg
  pinout: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Display-S3/main/image/T-DISPLAY-S3.jpg
platformio_definitions:
- id: lilygo-t-display-s3
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: d9fe90c0e4768e121cd849ab218e91b0f98309504ae8edfc9c4f1d7c60830a7a
- id: lilygo-t-display-s3
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: dc87dc7fa6359e16e05564a7f0271f671fc6cadb66821f2f54ca9be15de94e37
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-display-s3
  verified: '2026-08-21'
- field: '*'
  url: https://github.com/Xinyuan-LilyGO/T-Display-S3
  verified: '2026-08-21'
- field: io.power_out
  url: https://github.com/Xinyuan-LilyGO/T-Display-S3
  verified: '2026-08-26'
- field: usb_serial
  url: https://www.lilygo.cc/products/t-display-s3
  verified: '2026-09-07'
- field: getting_started
  url: https://lilygo.cc/products/t-display-s3
  verified: '2026-09-11'
- field: images
  url: https://lilygo.cc/products/t-display-s3
  verified: '2026-09-12'
- field: images.pinout
  url: https://raw.githubusercontent.com/Xinyuan-LilyGO/T-Display-S3/main/image/T-DISPLAY-S3.jpg
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/lilygo-t-display-s3.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/lilygo-t-display-s3.json
  verified: '2026-11-22'
---

# T-Display-S3

ESP32-S3R8 dev board with a 1.9in 170x320 ST7789V IPS display, native USB-C, and JST battery charging.
