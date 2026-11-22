---
id: lilygo-t-display
type: board
brand: lilygo
name: T-Display
soc: esp32
psram_mb: 0
form_factor: t-display
price_tier: medium
usb:
  bridge: ch9102
usb_serial: ch9102
display: 1.14in 135x240 ST7789 SPI IPS
notes:
- 4 MB or 16 MB flash options (board-level default/most-common SKU not confirmed in
  vendor docs, so flash_mb is left unset)
- Onboard battery power detection circuit
- Wi-Fi 802.11 b/g/n, Bluetooth v4.2+BLE
- LilyGO's official Arduino IDE setup guide instructs users to select "Disable" for
  PSRAM, confirming this board has none
- 'io OMITTED: the official README''s "Pinout" table only lists pins consumed by the
  onboard ST7789 display/I2C/buttons/battery ADC (TFT_MOSI=19, TFT_SCLK=18, TFT_CS=5,
  TFT_DC=16, TFT_RST=23, TFT_BL=4, I2C_SDA=21, I2C_SCL=22, ADC_IN=34, BUTTON1=35,
  BUTTON2=0, ADC Power=14); it states no total exposed-pad count and no full side-header
  pin list, and no other official LilyGo page/schematic-checklist source was found
  with one, so gpio_exposed/gpio_free are left unset per cite-or-omit'
- usb_serial derived from usb.bridge (ch9102)
getting_started: https://lilygo.cc/products/t-display
images:
  photo: https://lilygo.cc/cdn/shop/files/LILYGO-T-DISPLAY_5_cd0e2152-00a0-4403-a557-f96f6ba0d1e4.jpg
  pinout: https://raw.githubusercontent.com/Xinyuan-LilyGO/TTGO-T-Display/master/image/pinmap.jpg
platformio_definitions:
- id: lilygo-t-display
  platform_package: platformio/espressif32@8.0.0
  manifest_digest: e09444284e73f2d503a31e7cb3d430eac17932efebfee1ad56f71a60807c878b
- id: lilygo-t-display
  platform_package: https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip
  manifest_digest: 59a0eba28df6922530be2c330e15f3149bd982241d1e3542a86d0a7af66aab50
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-display
  verified: '2026-08-22'
- field: psram_mb
  url: https://github.com/Xinyuan-LilyGO/TTGO-T-Display/blob/master/README.MD
  verified: '2026-08-24'
- field: usb_serial
  url: https://www.lilygo.cc/products/t-display
  verified: '2026-09-07'
- field: getting_started
  url: https://lilygo.cc/products/t-display
  verified: '2026-09-11'
- field: images
  url: https://lilygo.cc/products/t-display
  verified: '2026-09-12'
- field: images.pinout
  url: https://raw.githubusercontent.com/Xinyuan-LilyGO/TTGO-T-Display/master/image/pinmap.jpg
  verified: '2026-09-30'
- field: platformio_definitions
  url: https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/lilygo-t-display.json
  verified: '2026-11-22'
- field: platformio_definitions
  url: https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/lilygo-t-display.json
  verified: '2026-11-22'
---

# T-Display

Original ESP32 dev board with a 1.14in 135x240 ST7789 SPI IPS display and a CH9102 USB-serial bridge.
