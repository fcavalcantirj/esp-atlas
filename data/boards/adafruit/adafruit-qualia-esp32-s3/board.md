---
id: adafruit-qualia-esp32-s3
type: board
brand: adafruit
name: Adafruit Qualia ESP32-S3 for RGB-666 Displays
aka:
- adafruit_qualia_s3_rgb666
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: qualia
price_tier: medium
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
extras:
- stemma-qt
notes:
- ESP32-S3 driver board for external 40-pin RGB-666 TTL displays (no onboard display).
- 'flash_mb=16 QUOTED: "16 MB of Flash". psram_mb=8 QUOTED: "8 MB of octal PSRAM".'
- 'soc=esp32-s3 / usb.connector=usb-c / bridge=native / usb_serial QUOTED: "Power
  and programming is provided over a USB C connector, wired to the S3''s native USB
  port."'
- 'display field omitted: Qualia drives external RGB-666 panels rather than an
  onboard display. QUOTED interface: "16 pins connected to the TFT for 5-6-5 RGB
  color, plus HSync, VSync, Data Enable and Pixel Clock" via a "40-pin RGB-666
  connector".'
- 'extras QUOTED: stemma-qt "we provide a Stemma QT / Qwiic port". microSD not
  recorded as an onboard slot -- QUOTED only "enough to wire up an MMC in 1-wire
  SDIO mode" (a capability, not a fitted slot).'
- 'power omitted: no battery connector/charging stated. dimensions_mm omitted: not
  stated in mm. io omitted: no explicit broken-out GPIO count.'
getting_started: https://learn.adafruit.com/adafruit-qualia-esp32-s3-for-rgb666-displays
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-qualia-esp32-s3-for-rgb666-displays
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-qualia-esp32-s3-for-rgb666-displays
  verified: '2026-09-11'
---

# Adafruit Qualia ESP32-S3 for RGB-666 Displays

ESP32-S3 driver board with native USB-C, 16 MB flash / 8 MB octal PSRAM, a 40-pin RGB-666 TTL display connector, and STEMMA QT.
