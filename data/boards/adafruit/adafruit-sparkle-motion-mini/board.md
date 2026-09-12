---
id: adafruit-sparkle-motion-mini
type: board
brand: adafruit
name: Adafruit Sparkle Motion Mini
aka:
- sparklemotionmini
soc: esp32
flash_mb: 4
dimensions_mm:
- 30.0
- 20.0
usb:
  connector: usb-c
extras:
- level-shifter
- mic
- rgb-led
- stemma-qt
notes:
- '4 MB flash; PSRAM not stated (omitted). Vendor: "ESP32 mini module with built in
  antenna port ... Comes with 4 MB of flash, dual core 240MHz Tensilica, WiFi, Bluetooth
  LE and Bluetooth Classic support"'
- 'USB Type C connector. Vendor states "USB-serial converter with auto-reset" but
  does not name the bridge chip model, so usb_serial is set to usb-uart-bridge-unspecified'
- 'Power (power object omitted -- no onboard LiPo battery connector/charger stated):
  "Power via USB Type C for up to 5V 4A input - you can use off-the-shelf USB battery
  packs for portable operation"; "4 Amp resetting fuse to protect from over-current
  drive"'
- 'extras from vendor bullets: "Two output signals plus 5V power and ground - both
  signal output are level shifted to 5V" (level-shifter); "Built-in I2S microphone
  type SPH0654" (mic); "Small built-in NeoPixel on pin 18" (rgb-led); "Stemma QT I2C
  port to connect external sensors/OLED/etc" (stemma-qt). NOT included: screw-terminals
  -- "To keep the design slim we don''t include terminal blocks pre-soldered"; ir-receiver
  -- only an "external IR receiver" via the JST input port is mentioned, no built-in
  one. Also present but not modeled: "Red built-in LED on pin 12" and "User button
  on GPIO 0 plus Reset button"'
- 'io omitted: vendor lists "Two output signals plus 5V power and ground" and "Extra
  2x3 0.1" breakout pads with 4 more GPIO plus 3V power and ground" but prints no single
  explicit usable-GPIO count'
- 'Dimensions vendor-stated: "1.2"x0.8" / 30mm x 20mm size with mounting holes"'
- 'download_mode auto: vendor states "USB-serial converter with auto-reset"'
- 'form_factor omitted: an LED-strip controller does not match any established form_factor
  value in the catalog'
download_mode:
  mode: auto
getting_started: https://learn.adafruit.com/adafruit-sparkle-motion-mini
usb_serial: usb-uart-bridge-unspecified
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-sparkle-motion-mini
  verified: '2026-09-12'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/56a7eb7269a8dd524c72c6752adaaad7814a0766/boards.txt
  verified: '2026-09-12'
---

# Adafruit Sparkle Motion Mini

Compact ESP32 LED-strip controller (30x20mm) with USB-C power, two level-shifted outputs on 0.1" breakout pads, a built-in I2S mic, NeoPixel, and STEMMA QT.
