---
id: waveshare-esp32-s3-rlcd-42
type: board
brand: waveshare
name: ESP32-S3-RLCD-4.2
aka:
- "waveshare_rlcd42"
soc: esp32-s3
flash_mb: 16
psram_mb: 8
display: 4.2in 300x400 RLCD ST7305 (reflective, black/white)
power:
  battery_connector: true
  charging: true
extras:
- sd-card
- mic
- speaker
notes:
- 'Product page: "RLCD AIoT development board based on ESP32-S3"; "Built-in 512KB Static RAM, 384KB ROM, with integrated 16MB Flash and 8MB PSRAM"; the page does not name the ESP32-S3 sub-variant (soc only)'
- 'Display: "4.2inch RLCD, 300 x 400 resolution, features reflective imaging and no backlight required"; Driver IC "ST7305"; display color "black, white"'
- 'Onboard "dual-microphone array", speaker, "PCF85063 RTC chip and SHTC3 temperature & humidity sensor", "18650 Lithium Batt holder", "Lithium Batt charging and discharging management circuit", "TF card slot", "programmable KEY and BOOT side buttons"'
- USB connector type is not stated in the product text captured (omitted); the wiki page for this board was still a placeholder on the verified date
- 'aka "waveshare_rlcd42" is the device token draftling uses for its release binaries'
sources:
- field: '*'
  url: https://www.waveshare.com/esp32-s3-rlcd-4.2.htm
  verified: '2026-09-07'
- field: aka
  url: https://github.com/clackups/draftling/releases/tag/v1.0.1
  verified: '2026-09-07'
---

# Waveshare ESP32-S3-RLCD-4.2

A 4.2-inch reflective-LCD board on an ESP32-S3 (16 MB flash, 8 MB PSRAM) with dual microphones, a speaker, an 18650 holder and a TF-card slot.
