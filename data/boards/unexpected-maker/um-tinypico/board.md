---
id: um-tinypico
type: board
brand: unexpected-maker
name: TinyPICO
soc: esp32
form_factor: tinypico
price_tier: cheap
dimensions_mm:
- 35
- 17.8
notes:
- 'MCU: ESP32-PICO-D4 (2x Xtensa LX6, no native USB), 4 MB flash, 4 MB PSRAM — per Unexpected Maker''s official TinyS3/TinyS2/TinyPICO board comparison matrix'
- 'The comparison matrix lists the USB connector as "USB-C & Micro-B"; the exact split (data vs. power-only) is not itemized on the page, so usb.connector is left unset rather than guessed'
- 'Dimensions taken from the TinyS3 product page, which states the TinyS3 is "the same tiny package size as the original TinyPICO"; the original tinypico.com product page has since gone offline (404)'
- 'The original https://tinypico.com product page returns HTTP 404 as of this pass; no direct vendor product page could be found and confirmed live, so all specs here are sourced from Unexpected Maker''s TinyS3 comparison page instead'
sources:
- field: '*'
  url: https://esp32s3.com/tinys3.html
  verified: '2026-08-22'
---

# TinyPICO

Unexpected Maker's original tiny ESP32 board, built around the ESP32-PICO-D4 SoC. Predecessor to the TinyS3; its own dedicated product page is no longer live, so specs here are sourced from Unexpected Maker's TinyS3 comparison matrix, which documents the TinyPICO as a reference point.
