---
id: heltec-wifi-lora-32-v3
type: board
brand: heltec
name: WiFi LoRa 32 (V3)
soc: esp32-s3
flash_mb: 8
psram_mb: 0
form_factor: heltec
price_tier: medium
dimensions_mm:
- 50.2
- 25.5
- 10.2
usb:
  connector: usb-c
  bridge: cp2102
power:
  battery_connector: true
  charging: true
display: 0.96in 128x64 OLED
extras:
- lora
io:
  gpio_exposed: 28
  gpio_free: 18
notes:
- ESP32-S3FN8, 8 MB SiP flash, no external PSRAM
- SX1262 LoRa transceiver; IPEX antenna connector for LoRa, onboard metal spring 2.4 GHz WiFi/BT antenna
- 'io.gpio_exposed=28 QUOTED: Heltec''s WiFi LoRa 32 (V3) datasheet Pin Definition
  table lists Header J2 GPIO {44,43,36,35,34,33,47,48,26,21,20,19,0} (13 pins)
  and Header J3 GPIO {37,46,45,42,41,40,39,38,1,2,3,4,5,6,7} (15 pins) -- 28
  header-exposed pads total; the SX1262''s SPI bus (NSS/SCK/MOSI/MISO GPIO8-11,
  RST/BUSY/DIO1 GPIO12-14) and the OLED''s I2C data lines (SDA_OLED/SCL_OLED,
  GPIO17/18) are wired directly to the onboard radio/display and never reach
  either header'
- 'io.gpio_free=18 DERIVED: subtracting esp32-s3''s soc.reserved_pins that are
  exposed here (strapping {0,3,45,46}: all 4 present; usb_flash_tied {19,20,35,36,37}:
  all 5 present -- 9 total) and the OLED reset line shared with the header (GPIO21,
  labeled "OLED RST" in the datasheet) gives 28 - 9 - 1 = 18; the LoRa radio''s
  own SPI/control pins (GPIO8-14) cost nothing further since they never reached
  the header count in the first place'
sources:
- field: '*'
  url: https://heltec.org/project/wifi-lora-32-v3/
  verified: '2026-08-22'
- field: io.gpio_exposed
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V3/HTIT-WB32LA_V3(Rev1.1).pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://resource.heltec.cn/download/WiFi_LoRa_32_V3/HTIT-WB32LA_V3(Rev1.1).pdf
  verified: '2026-08-26'
- field: io.gpio_free
  url: https://github.com/espressif/arduino-esp32/blob/master/variants/heltec_wifi_lora_32_V3/pins_arduino.h
  verified: '2026-08-26'
---

# WiFi LoRa 32 (V3)

ESP32-S3FN8 + SX1262 LoRa dev board with a 0.96in OLED, native USB-C, and lithium battery charging. Meshtastic and LoRaWAN compatible.
