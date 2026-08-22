---
id: um-feathers2
type: board
brand: unexpected-maker
name: FeatherS2
soc: esp32-s2
form_factor: feather
price_tier: medium
usb:
  bridge: native
power:
  battery_connector: true
  charging: true
extras:
- rgb-led
- stemma-qt
notes:
- 16 MB flash, 8 MB PSRAM, native USB (CDC & OTG) — no Bluetooth on the ESP32-S2
- Two 700 mA 3.3V LDO regulators; the second LDO powers the onboard APA-102 RGB LED and external 3V3 peripherals, with GPIO21-controlled auto shutdown in deep sleep
- One STEMMA QT (I2C) connector
- LiPo battery charging circuit; exact connector type and board dimensions are not stated on either sourced page and are omitted
sources:
- field: '*'
  url: https://feathers2.io/
  verified: '2026-08-22'
- field: extras
  url: https://esp32s3.com/feathers3.html
  verified: '2026-08-22'
---

# FeatherS2

Unexpected Maker's ESP32-S2 board in the Adafruit Feather format, with 16 MB flash, 8 MB PSRAM, native USB, an APA-102 RGB LED, one STEMMA QT connector, and LiPo charging.
