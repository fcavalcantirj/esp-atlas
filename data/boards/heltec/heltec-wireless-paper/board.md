---
id: heltec-wireless-paper
type: board
brand: heltec
name: Wireless Paper
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: heltec
price_tier: cheap
dimensions_mm:
- 88
- 88
- 25
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 2.13in 122x250 E-Ink
extras:
- lora
- e-ink
io:
  gpio_exposed: 28
  gpio_free: 14
notes:
- ESP32-S3FN8
- SX1262 LoRa transceiver, user-selectable 433/470-510/863-870/902-928 MHz bands
- E-Ink image persists ~180 days without power; drag-and-drop BMP refresh
- ESP32-S3FN8 ordering code is 8 MB in-package flash with no PSRAM, per Espressif's ESP32-S3 series datasheet
- 'io.gpio_exposed=28 DERIVED: Heltec''s Wireless Paper datasheet omits the Pin
  Definition/header table its sibling V3 boards publish, but the schematic diagram
  shows the same GPIO roster (GPIO0-7, 33-42, 45-46 plus TX/RX) wired to the
  identical 2x-header (J2+J3) carrier confirmed by name-for-name matching Pin
  Definition tables in the WiFi Kit 32 (V3), WiFi LoRa 32 (V3), and Wireless
  Stick (V3) datasheets -- each independently states 28 header-exposed GPIO
  pads on that shared carrier design, so the family total is applied here'
- 'io.gpio_free=14 DERIVED: subtracting esp32-s3''s soc.reserved_pins that are
  exposed here (strapping {0,3,45,46}: all 4 present; usb_flash_tied {19,20,35,36,37}:
  all 5 present -- 9 total) and the E-Ink panel''s SPI bus -- the official example
  sketch (Wireless_Paper_V1.0.ino) constructs the display driver as
  QYEG0213RWS800_BWR(rst=6, dc=5, cs=4, busy=7, sck=3, mosi=2); GPIO3 is already
  removed via reserved_pins so the new subtraction is {2,4,5,6,7} (5 pins) --
  gives 28 - 9 - 5 = 14; the SX1262 LoRa radio''s own SPI/control pins (GPIO8-14)
  are wired off-header as on the sibling boards and cost nothing further'
sources:
- field: '*'
  url: https://heltec.org/project/wireless-paper/
  verified: '2026-08-22'
- field: flash_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-08-24'
- field: psram_mb
  url: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
  verified: '2026-08-24'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/Wireless_Paper/Wireless_Paper_V0.4_Schematic_Diagram.pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/HelTecAutomation/Heltec_ESP32/blob/master/examples/Wireless_paper/Wireless_Paper_V1.0/Wireless_Paper_V1.0.ino
  verified: '2026-08-26'
---

# Wireless Paper

ESP32-S3FN8 + SX1262 LoRa dev board with a 2.13in E-Ink display, USB-C, and lithium battery charging — built for ultra-low-power always-on displays.
