---
id: lcdwiki-es3c28p
type: board
brand: lcdwiki
name: ES3C28P (2.8-inch ESP32-S3 Display)
aka:
- ES3C28P
soc: esp32-s3
flash_mb: 16
psram_mb: 8
dimensions_mm: [50, 86, 10.6]
usb:
  connector: usb-c
power:
  battery_connector: true
  charging: true
display: 2.8in 240x320 IPS ILI9341V (FT6336G capacitive touch)
extras:
- sd-card
- mic
- rgb-led
notes:
- This record covers the capacitive-touch SKU.
- The schematic identifies bare ESP32-S3R8 chip U7 and an external SPI flash chip.
getting_started: https://www.lcdwiki.com/2.8inch_ESP32-S3_Display
sources:
- field: '*'
  url: 'https://www.lcdwiki.com/index.php?title=2.8inch_ESP32-S3_Display&oldid=6127'
  verified: '2026-11-05'
- field: soc
  url: https://www.lcdwiki.com/res/ES3C28P/2.8inch_ESP32-S3_Display_Schematic.pdf
  verified: '2026-11-05'
---

# LCDWIKI ES3C28P

An ESP32-S3 display board with a 2.8-inch capacitive touch screen, microphone,
microSD slot and battery charging. This record covers the ES3C28P touch variant.
