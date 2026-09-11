---
id: adafruit-pycamera-s3
type: board
brand: adafruit
name: Adafruit pyCamera S3 (MEMENTO)
aka:
- adafruit_camera_esp32s3
soc: esp32-s3
flash_mb: 4
psram_mb: 2
form_factor: memento
price_tier: medium
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 1.54in 240x240 Color TFT
extras:
- camera
- mic
- accelerometer
- stemma-qt
- sd-card
notes:
- ESP32-S3 camera board retailed as the Adafruit MEMENTO.
- 'soc/flash/psram QUOTED: "ESP32-S3 module with 4 MB Flash, 2 MB PSRAM".'
- 'usb.connector=usb-c QUOTED: "USB Type C". usb.bridge/usb_serial omitted: the
  guide does not explicitly state native-USB flashing wording, so left uncited
  rather than assumed.'
- 'power QUOTED: "LiPoly battery charging support" and "Use a 3.7/4.2V 350mA or
  420mA battery".'
- 'display QUOTED: "1.54" 240x240 Color TFT".'
- 'extras QUOTED: camera "OV5640 camera module with 72 degree view and auto-focus
  motor"; mic "Analog Microphone"; accelerometer "LIS3DH Accelerometer"; stemma-qt
  "I2C Stemma QT Port"; sd-card "MicroSD card slot".'
- 'dimensions_mm omitted: not stated in mm on the guide. io omitted: no explicit
  broken-out GPIO count.'
getting_started: https://learn.adafruit.com/adafruit-memento-camera-board
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-memento-camera-board
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-memento-camera-board
  verified: '2026-09-11'
---

# Adafruit pyCamera S3 (MEMENTO)

ESP32-S3 DIY camera board with an OV5640 sensor, 1.54in color TFT, analog mic, LIS3DH accelerometer, microSD, and STEMMA QT.
