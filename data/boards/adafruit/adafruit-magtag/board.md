---
id: adafruit-magtag
type: board
brand: adafruit
name: Adafruit MagTag 2.9" Grayscale E-Ink WiFi Display
aka:
- adafruit_magtag29_esp32s2
soc: esp32-s2
flash_mb: 4
psram_mb: 2
form_factor: magtag
price_tier: medium
usb:
  connector: usb-c
  bridge: native
power:
  battery_connector: true
  charging: true
display: 2.9in 296x128 grayscale E-Ink
extras:
- rgb-led
- accelerometer
- speaker
- light-sensor
- stemma-qt
notes:
- ESP32-S2 board with a 2.9" grayscale E-Ink display.
- 'soc=esp32-s2 QUOTED: "ESP32-S2 240MHz Tensilica processor". flash_mb=4 QUOTED:
  "4 MByte of Flash". psram_mb=2 QUOTED: "2 MByte of PSRAM".'
- 'usb.connector=usb-c / bridge=native QUOTED: "USB C power and data connector" and
  "native USB so it can act like a keyboard/mouse, MIDI device, disk drive, etc".
  usb_serial omitted: esp32-s2 has USB-OTG only (no USB-Serial-JTAG peripheral).'
- 'power QUOTED: "a spot for a 350 or 420 mAh battery and built in battery charging
  over USB C".'
- 'display QUOTED: "2.9" grayscale display with 296x128 pixels. Each pixel can be
  white, light gray, dark gray or black".'
- 'extras QUOTED: rgb-led "Four RGB side-emitting NeoPixels"; accelerometer
  "Triple-axis accelerometer (LIS3DH)"; speaker "Speaker/Buzzer with mini class D
  amplifier"; light-sensor "Front facing light sensor"; stemma-qt "STEMMA QT port".
  ("Four buttons" also present but not listed as a peripheral extra.)'
- 'dimensions_mm omitted: not stated in mm. io omitted: no explicit broken-out GPIO
  count.'
getting_started: https://learn.adafruit.com/adafruit-magtag
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-magtag
  verified: '2026-09-11'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/6048a624f084ea7f645384fd91c57f43e633875d/boards.txt
  verified: '2026-09-11'
- field: getting_started
  url: https://learn.adafruit.com/adafruit-magtag
  verified: '2026-09-11'
---

# Adafruit MagTag

ESP32-S2 board with a 2.9in 296x128 grayscale E-Ink display, four NeoPixels, LIS3DH accelerometer, speaker, light sensor, LiPoly charging, and STEMMA QT.
