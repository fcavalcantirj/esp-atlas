---
id: adafruit-sparkle-motion-stick
type: board
brand: adafruit
name: Adafruit Sparkle Motion Stick
aka:
- sparklemotionstick
soc: esp32
flash_mb: 4
extras:
- screw-terminals
- level-shifter
- ir-receiver
- mic
- rgb-led
notes:
- '4 MB flash; PSRAM not stated (omitted). Vendor: "ESP32 mini module with built in
  antenna port ... Comes with 4 MB of flash", "dual-core 240MHz Tensilica", "WiFi,
  Bluetooth LE, and Bluetooth Classic support"'
- 'usb object omitted: vendor states "Power via USB Type A for up to 5V 2A input"
  -- the board plugs directly into a host USB Type A port, and "usb-a" is not an allowed
  usb.connector enum value (usb-c/micro-usb/mini-usb/none), so the field is omitted
  rather than set to an invalid value. Vendor also states "USB-serial converter with
  auto-reset" but does not name the bridge chip, so usb_serial is set to usb-uart-bridge-unspecified'
- 'Power (power object omitted -- no onboard LiPo battery connector/charger stated):
  "Power via USB Type A for up to 5V 2A input" (portable via USB battery packs); "2
  Amp resetting fuse to protect from over-current drive"'
- 'extras from vendor bullets: "Screw terminal blocks for no-solder connectivity"
  (screw-terminals); "Two output signals plus 5V power and ground" with "both signal
  outputs are level shifted to 5V" (level-shifter); "Built-in Infrared receiver on
  GPIO 10" (ir-receiver); "Built-in I2S microphone for audio-reactive projects" (mic);
  "Small built-in NeoPixel on pin 18" (rgb-led). STEMMA QT is NOT stated for this board
  (omitted). Also present but not modeled: "Red built-in LED on pin 4" and "User button
  on GPIO 0"'
- 'io omitted: no explicit usable-GPIO count is printed on the page'
- 'Dimensions omitted: not stated in mm on the page'
- 'download_mode auto: vendor states "USB-serial converter with auto-reset"'
- 'form_factor omitted: an LED-controller stick does not match any established form_factor
  value in the catalog'
download_mode:
  mode: auto
getting_started: https://learn.adafruit.com/adafruit-sparkle-motion-stick
usb_serial: usb-uart-bridge-unspecified
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-sparkle-motion-stick
  verified: '2026-09-12'
- field: aka
  url: https://raw.githubusercontent.com/espressif/arduino-esp32/56a7eb7269a8dd524c72c6752adaaad7814a0766/boards.txt
  verified: '2026-09-12'
---

# Adafruit Sparkle Motion Stick

Stick-form ESP32 LED controller that plugs into a USB Type A port, with screw-terminal level-shifted outputs, a built-in I2S mic, IR receiver on GPIO 10, and NeoPixel.
