---
id: adafruit-funhouse
type: board
brand: adafruit
name: Adafruit FunHouse
aka:
- adafruit_funhouse_esp32s2
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: funhouse
price_tier: medium
usb:
  connector: usb-c
  bridge: native
display: 1.54in 240x240 Color TFT
extras:
- dps310
- aht20
- light-sensor
- capacitive-touch
- buzzer
- rgb-led
- stemma-qt
notes:
- ESP32-S2 WiFi home-automation dev board with an onboard TFT and sensors.
- 'soc=esp32-s2 QUOTED: "ESP32-S2 240MHz Tensilica processor". flash_mb=4 QUOTED:
  "4 MByte of Flash". psram_mb=2 QUOTED: "2 MByte of PSRAM".'
- 'usb.connector=usb-c / bridge=native QUOTED: "USB C" and "native USB so it can
  act like a keyboard/mouse, MIDI device, disk drive". usb_serial omitted: esp32-s2
  has USB-OTG only (no USB-Serial-JTAG peripheral).'
- 'display QUOTED: "1.54" Color TFT display with 240x240 pixels".'
- 'extras QUOTED: dps310 "DPS310 barometric pressure and temperature sensor"; aht20
  "AHT20 relative humidity and temperature sensor"; light-sensor "Front facing
  light sensor"; capacitive-touch "Three capacitive touch pads and one capacitive
  touch slider"; buzzer "Speaker/Buzzer can play tones and beeps"; rgb-led "Five
  mini RGB DotStar LEDs"; stemma-qt "STEMMA QT port".'
- 'A "Plug in socket for Mini PIR sensor (not included)" and "Three STEMMA 3 pin
  JST connectors" are provided but the PIR is not an onboard-fitted sensor, so it
  is not listed under extras.'
- 'power omitted: no battery connector/charging stated (USB-powered). dimensions_mm
  omitted: not stated in mm. io omitted: no explicit broken-out GPIO count.'
getting_started: https://learn.adafruit.com/adafruit-funhouse
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-funhouse
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-funhouse
  verified: '2026-09-11'
---

# Adafruit FunHouse

ESP32-S2 home-automation dev board with a 1.54in 240x240 TFT, DPS310/AHT20 sensors, capacitive touch, DotStar LEDs, buzzer, and STEMMA QT.
