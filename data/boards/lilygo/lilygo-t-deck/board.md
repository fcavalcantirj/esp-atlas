---
id: lilygo-t-deck
type: board
brand: lilygo
name: T-Deck
soc: esp32-s3
flash_mb: 16
psram_mb: 8
form_factor: t-deck
price_tier: medium
display: 2.8in 320x240 ST7789 SPI IPS
extras:
- lora
- keyboard
- trackball
- microphone
- speaker
io:
  gpio_exposed: 4
  gpio_free: 3
notes:
- ESP32-S3FN16R8 dual-core LX7; 16 MB flash, 8 MB PSRAM
- 'LoRa transceiver: SX1262 (chip-optional SKU), +22dBm, 433/868/915MHz'
- Onboard mini keyboard (shipped in a randomly-selected color/layout)
- Wi-Fi 2.4GHz + Bluetooth 5 (LE)
- 'io.gpio_exposed=4 QUOTED: the vendor firmware repo''s own board pin-definition
  header (utilities.h) defines exactly 4 undocumented GPIOs -- BOARD_TBOX_G01=3,
  G02=2, G03=15, G04=1 -- claimed by no other onboard peripheral in that file;
  the official README confirms base T-Deck (non-Plus) ships a user-facing Grove
  HY2.0-4P interface that is free/unassigned (Plus variant reassigns it to GPS),
  matching this G01-G04 naming. io.gpio_free=3 DERIVED: subtracting esp32-s3''s
  soc.reserved_pins -- GPIO3 (G01) is a strapping pin, GPIO2/15/1 are not
  strapping or usb_flash_tied -- gives 4 - 1 = 3'
sources:
- field: '*'
  url: https://www.lilygo.cc/products/t-deck
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://github.com/Xinyuan-LilyGO/T-Deck/blob/master/examples/UnitTest/utilities.h
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/Xinyuan-LilyGO/T-Deck/blob/master/examples/UnitTest/utilities.h
  verified: '2026-08-26'
---

# T-Deck

ESP32-S3FN16R8 handheld with a 2.8in ST7789 IPS display, onboard keyboard, trackball, mic/speaker, and an optional SX1262 LoRa transceiver.
