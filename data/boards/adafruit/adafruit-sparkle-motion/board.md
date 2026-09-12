---
id: adafruit-sparkle-motion
type: board
brand: adafruit
name: Adafruit Sparkle Motion
aka:
- sparklemotion
soc: esp32
flash_mb: 4
dimensions_mm:
- 33.0
- 45.0
usb:
  connector: usb-c
extras:
- screw-terminals
- level-shifter
- ir-receiver
- mic
- rgb-led
- stemma-qt
notes:
- '4 MB flash; PSRAM not stated (omitted). Vendor: "ESP32 mini module with built in
  antenna port" with "4 MB of flash, dual core 240MHz Tensilica, WiFi, Bluetooth LE
  and Bluetooth Classic support"'
- 'USB Type C connector. Vendor states "USB-serial converter with auto-reset" but
  does not name the bridge chip model, so usb_serial is set to usb-uart-bridge-unspecified'
- 'Power (power object omitted -- no onboard LiPo battery connector/charger stated):
  "Power option 1 via USB Type C PD with a slide switch that selects between 5, 12
  and 20V"; "Power option 2 via 2.1mm DC jack, center positive"; "Low forward-voltage
  diodes so its good for up to 5A from either"; "5 Amp fuse to protect from over-current
  drive"'
- 'extras from vendor bullets: "Three output signal terminal block sets with power
  and ground for each" (screw-terminals); "6 GPIO breakout pads with a fourth level-shifted
  output" (level-shifter); "Built-in IR receiver for easy remote control integration"
  (ir-receiver); "Built-in I2S microphone for audio-reactive projects" (mic); "Small
  built-in NeoPixel on pin 2" (rgb-led); "Stemma QT I2C port to connect external sensors/OLED/etc"
  (stemma-qt). Also present but not modeled as extras: "Red built-in LED on pin 4"
  and "User button on GPIO 0 plus Reset button"'
- 'io omitted: vendor lists "6 GPIO breakout pads with a fourth level-shifted output,
  and 3 more GPIO plus power and ground" but prints no single explicit usable-GPIO
  count'
- 'Dimensions vendor-stated: "1.3"x1.75" / 33mm x 45mm"'
- 'download_mode auto: vendor states "USB-serial converter with auto-reset"'
- 'form_factor omitted: an LED-strip controller does not match any established form_factor
  value in the catalog'
download_mode:
  mode: auto
getting_started: https://learn.adafruit.com/adafruit-sparkle-motion
usb_serial: usb-uart-bridge-unspecified
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-sparkle-motion
  verified: '2026-09-12'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/56a7eb7269a8dd524c72c6752adaaad7814a0766/boards.txt
  verified: '2026-09-12'
---

# Adafruit Sparkle Motion

ESP32-based LED-strip controller with USB-C PD (5/12/20V) or 2.1mm DC-jack power, three level-shifted terminal-block outputs, a built-in I2S mic, IR receiver, NeoPixel, and STEMMA QT.
