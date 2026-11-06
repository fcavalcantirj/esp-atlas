---
id: freenove-fnk0104s
type: board
brand: freenove
name: ESP32-S3 Display FNK0104S
aka:
- freenove_fnk0104s
soc: esp32-s3
display: 4.0in 320x480 touch
notes:
- 'Display controller UNVERIFIED: the vendor repo README labels FNK0104S ST7789,
  while Freenove''s model guide and touch-drawing sketch label FNK0104S ST7796.
  The vendor sources conflict, so neither controller is asserted.'
- The store listing (SKU FNK0104S) titles the line "Freenove ESP32 Touch Display
  ESP32-S3 CYD Wi-Fi Bluetooth, 2.8 3.5 4.0 Inch IPS Touch Screen, Dual-core
  32-bit 240 MHz"
- Flash, PSRAM, module, USB connector and battery are not verified here (omitted)
- aka "freenove_fnk0104s" is the device token draftling uses for its release binaries
getting_started: https://docs.freenove.com/projects/fnk0104/en/latest/
images:
  pinout: https://raw.githubusercontent.com/Freenove/Freenove_ESP32_S3_Display/main/Picture/FNK0104S_Bottom.png
sources:
- field: '*'
  url: https://github.com/Freenove/Freenove_ESP32_S3_Display
  verified: '2026-09-07'
- field: display
  url: https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/Freenove_ESP32S3_Display.html
  verified: '2026-11-06'
- field: display
  url: https://github.com/Freenove/Freenove_ESP32_S3_Display/blob/90004f874ed567b3c09d534d021172cb716e61a1/README.md#L17
  verified: '2026-11-06'
- field: notes
  url: https://github.com/Freenove/Freenove_ESP32_S3_Display/blob/90004f874ed567b3c09d534d021172cb716e61a1/README.md#L17
  verified: '2026-11-06'
- field: notes
  url: https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/Freenove_ESP32S3_Display.html
  verified: '2026-11-06'
- field: notes
  url: https://docs.freenove.com/projects/fnk0104/en/latest/fnk0104/codes/MAIN/12_TFT_Touch_Drawing.html
  verified: '2026-11-06'
- field: soc
  url: https://store.freenove.com/products/fnk0104
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
- field: getting_started
  url: https://docs.freenove.com/projects/fnk0104/en/latest/
  verified: '2026-09-12'
- field: images.pinout
  url: https://raw.githubusercontent.com/Freenove/Freenove_ESP32_S3_Display/main/Picture/FNK0104S_Bottom.png
  verified: '2026-09-30'
---

# Freenove ESP32-S3 Display FNK0104S

The 4.0 inch 320x480 touch variant of Freenove's ESP32-S3 display board line.
Freenove's own sources disagree on the display controller, so that value remains unverified.
