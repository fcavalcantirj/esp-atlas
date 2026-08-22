# Board Coverage Backlog

This is the master tracking list for covering every ESP32-family board across
the vendors that make them. It is a **checklist of names and source URLs**,
nothing else — it contains zero hardware specs. Specs are added later, per
board, in `data/boards/<brand>/<board-id>/board.md`.

**Hard rule (same as the rest of the repo):** when a board here graduates
from `[ ]` to `[x]`, its `board.md` must cite an official datasheet or
vendor product-page source for every spec field — see
[CONTRIBUTING.md](CONTRIBUTING.md). No guessing, no filling in numbers from
memory. If a source can't be verified, the field is omitted, not invented.

This file itself follows the same honesty rule one level up: every entry
below is a board the author is genuinely confident exists. Where the exact
product-page URL wasn't known at write time, it's marked
`(url: to-verify)` rather than fabricated. No model numbers are invented.

**Progress: 39 boards done (out of an estimated 90+ known ESP32-family
boards across these vendors — the total will firm up as each vendor
section gets a real audit).**

---

## Espressif

Official site: https://www.espressif.com/en/products/devkits

- [x] ESP32-DevKitC V4 — https://www.espressif.com/en/products/devkits/esp32-devkitc
- [x] ESP32-S3-DevKitC-1 — https://www.espressif.com/en/products/devkits/esp32-s3-devkitc-1
- [x] ESP32-C6-DevKitC-1 — https://www.espressif.com/en/products/devkits/esp32-c6-devkitc-1
- [x] ESP32-C3-DevKitC-02 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitc-02/user_guide.html
- [x] ESP32-C3-DevKitM-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html
- [x] ESP32-S2-DevKitC-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-devkitc-1/user_guide.html
- [x] ESP32-S2-Saola-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html
- [x] ESP32-S3-DevKitM-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitm-1/user_guide.html
- [ ] ESP32-C61-DevKitC-1 — (url: to-verify)
- [ ] ESP32-C5-DevKitC-1 — (url: to-verify)
- [x] ESP32-H2-DevKitM-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32h2/esp32-h2-devkitm-1/user_guide.html
- [x] ESP-WROVER-KIT — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp-wrover-kit/user_guide.html
- [x] ESP32-DevKitM-1 — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitm-1/user_guide.html
- [x] ESP32-PICO-KIT — https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-pico-kit/user_guide.html
- [ ] ESP32-Ethernet-Kit — (url: to-verify)
- [ ] ESP32-LyraT / ESP32-LyraTD (audio dev boards) — (url: to-verify)

## Seeed Studio

Official site: https://www.seeedstudio.com/

- [x] Seeed Studio XIAO ESP32C3 — https://www.seeedstudio.com/Seeed-XIAO-ESP32C3-p-5431.html
- [x] Seeed Studio XIAO ESP32C6 — https://www.seeedstudio.com/Seeed-Studio-XIAO-ESP32C6-p-5884.html
- [x] Seeed Studio XIAO ESP32S3 — https://www.seeedstudio.com/Seeed-Studio-XIAO-ESP32S3-p-5627.html
- [ ] Seeed Studio XIAO ESP32S3 Sense (camera + mic variant) — https://www.seeedstudio.com/Seeed-Studio-XIAO-ESP32S3-Sense-p-5639.html
- [ ] Seeed Studio XIAO ESP32C3 Plus — (url: to-verify)
- [ ] Wio Terminal (ESP32-based variant, if applicable) — (url: to-verify)
- [ ] Seeed Studio Round Display for XIAO (carrier, not a standalone board) — (url: to-verify)

## Adafruit

Official site: https://www.adafruit.com/

- [x] Adafruit ESP32-S3 Feather (4MB Flash 2MB PSRAM) — https://www.adafruit.com/product/5477
- [x] Adafruit HUZZAH32 – ESP32 Feather Board — https://www.adafruit.com/product/3591
- [ ] Adafruit HUZZAH32 Breakout Board / ESP32 Feather — (url: to-verify; distinct
  bare-breakout SKU from the pre-soldered Feather board above, not yet confirmed)
- [x] Adafruit QT Py ESP32-S3 — https://www.adafruit.com/product/5426
- [x] Adafruit QT Py ESP32-S2 — https://www.adafruit.com/product/5325
- [x] Adafruit QT Py ESP32-C3 — https://www.adafruit.com/product/5405
- [ ] Adafruit MagTag (ESP32-S2) — https://www.adafruit.com/product/4800
- [ ] Adafruit Metro ESP32-S2 — https://www.adafruit.com/product/4775
- [x] Adafruit Feather ESP32-S2 — https://www.adafruit.com/product/5000
- [ ] Adafruit Feather ESP32-S2 TFT — https://www.adafruit.com/product/5300
- [ ] Adafruit Feather ESP32-S3 TFT — https://www.adafruit.com/product/5483
- [x] Adafruit Feather ESP32-S3 Reverse TFT — https://www.adafruit.com/product/5691
- [x] Adafruit ESP32 Feather V2 — https://www.adafruit.com/product/5400
- [x] Adafruit Metro ESP32-S3 — https://www.adafruit.com/product/5500
- [x] Adafruit MatrixPortal S3 — https://www.adafruit.com/product/5778
- [x] Adafruit ItsyBitsy ESP32 - PCB Antenna — https://www.adafruit.com/product/5889

## SparkFun

Official site: https://www.sparkfun.com/

- [x] SparkFun ESP32 Thing — https://www.sparkfun.com/sparkfun-esp32-thing.html
- [x] SparkFun Thing Plus - ESP32 WROOM (USB-C) — https://www.sparkfun.com/sparkfun-thing-plus-esp32-wroom-usb-c.html
- [ ] SparkFun ESP32 Thing Plus C — https://www.sparkfun.com/thing-plus-c-esp32-wroom.html
  (retired SKU WRL-16400-era predecessor; the page itself says it's been
  retired and points to the current WRL-20168 listing, which is the exact
  same physical product as "SparkFun Thing Plus - ESP32 WROOM (USB-C)"
  above. Not tracked as a separate board — would be a duplicate.)
- [x] SparkFun Thing Plus - ESP32-S2 WROOM — https://www.sparkfun.com/sparkfun-thing-plus-esp32-s2-wroom.html
- [ ] SparkFun ESP32-C6 Thing Plus — (url: to-verify)
- [x] SparkFun MicroMod ESP32 Processor — https://www.sparkfun.com/sparkfun-micromod-esp32-processor.html
- [x] SparkFun IoT RedBoard - ESP32 — https://www.sparkfun.com/sparkfun-iot-redboard-esp32-development-board.html

## LOLIN / Wemos

Official site: https://www.wemos.cc/

- [ ] LOLIN32 — (url: to-verify)
- [ ] LOLIN32 Lite — https://wiki.wemos.cc/products:lolin32:lolin32_lite (retired
  product; only listed on the wiki.wemos.cc subdomain, unreachable from the sandbox
  that did this pass — DNS/network block on that host specifically, www.wemos.cc
  resolved fine. Needs a follow-up pass with access to that host.)
- [x] LOLIN D32 — https://www.wemos.cc/en/latest/d32/d32.html
- [x] LOLIN D32 Pro — https://www.wemos.cc/en/latest/d32/d32_pro.html
- [x] LOLIN S2 Mini (ESP32-S2) — https://www.wemos.cc/en/latest/s2/s2_mini.html
- [ ] LOLIN S2 Pico (ESP32-S2) — (url: to-verify)
- [x] LOLIN S3 (ESP32-S3) — https://www.wemos.cc/en/latest/s3/s3.html
- [x] LOLIN S3 Mini (ESP32-S3) — https://www.wemos.cc/en/latest/s3/s3_mini.html
- [ ] LOLIN S3 Pro (ESP32-S3) — (url: to-verify)
- [x] LOLIN C3 Mini (ESP32-C3) — https://www.wemos.cc/en/latest/c3/c3_mini.html
- [ ] LOLIN C3 Pico (ESP32-C3) — (url: to-verify)

## Unexpected Maker

Official site: https://unexpectedmaker.com/

- [ ] TinyPICO (ESP32) — (url: to-verify)
- [ ] TinyS2 (ESP32-S2) — (url: to-verify)
- [ ] TinyS3 (ESP32-S3) — (url: to-verify)
- [ ] TinyC6 (ESP32-C6) — (url: to-verify)
- [ ] FeatherS2 (ESP32-S2) — (url: to-verify)
- [ ] FeatherS3 (ESP32-S3) — (url: to-verify)
- [ ] ProS3 (ESP32-S3) — (url: to-verify)
- [ ] Nano C6 (ESP32-C6) — (url: to-verify)

## M5Stack

Official site: https://www.m5stack.com/

- [x] M5Stack CoreS3 — https://shop.m5stack.com/products/m5stack-cores3-esp32s3-lotdevelopment-kit
- [ ] M5Stack Core2 (ESP32) — https://shop.m5stack.com/products/m5stack-core2-esp32-iot-development-kit
- [ ] M5Stack Core (Basic/Gray/Fire, ESP32) — (url: to-verify)
- [ ] M5StickC PLUS2 (ESP32) — https://shop.m5stack.com/products/m5stickc-plus2-esp32-mini-iot-development-kit
- [ ] M5StickC PLUS (ESP32) — (url: to-verify)
- [ ] M5Stamp C3 (ESP32-C3) — (url: to-verify)
- [ ] M5Stamp S3 (ESP32-S3) — (url: to-verify)
- [ ] M5Stamp Pico (ESP32) — (url: to-verify)
- [ ] M5Cardputer (ESP32-S3) — https://shop.m5stack.com/products/m5stack-cardputer-kit-w-m5stamps3
- [ ] M5Atom Lite / Matrix / Echo (ESP32) — (url: to-verify)
- [ ] M5AtomS3 (ESP32-S3) — https://shop.m5stack.com/products/atoms3-development-kit
- [ ] M5Dial (ESP32-S3) — (url: to-verify)
- [ ] M5NanoC6 (ESP32-C6) — (url: to-verify)

## LilyGO

Official site: https://www.lilygo.cc/

- [x] LilyGO T-Display-S3 — https://www.lilygo.cc/products/t-display-s3
- [ ] LilyGO T-Display (ESP32) — https://www.lilygo.cc/products/lilygo%C2%AE-ttgo-t-display-1-14-inch-lcd-esp32-control-board
- [ ] LilyGO T-Display-S3 AMOLED — (url: to-verify)
- [ ] LilyGO T-Watch (ESP32) — (url: to-verify)
- [ ] LilyGO T-Camera (ESP32) — (url: to-verify)
- [ ] LilyGO T7 (ESP32) — (url: to-verify)
- [ ] LilyGO T-QT (ESP32-S3) — (url: to-verify)
- [ ] LilyGO T-Dongle-S3 (ESP32-S3) — (url: to-verify)
- [ ] LilyGO TTGO T-Beam (ESP32 + LoRa) — (url: to-verify)
- [ ] LilyGO T-Deck (ESP32-S3) — (url: to-verify)

## Soldered (Dasduino / Inkplate)

Official site: https://soldered.com/

- [ ] Dasduino ConnectPlus (ESP32) — (url: to-verify)
- [ ] Dasduino Connect (ESP32) — (url: to-verify)
- [ ] Inkplate 6 (ESP32) — (url: to-verify)
- [ ] Inkplate 10 (ESP32) — (url: to-verify)
- [ ] Inkplate 6PLUS (ESP32) — (url: to-verify)
- [ ] Inkplate 2 (ESP32-C3) — (url: to-verify)

## DFRobot

Official site: https://www.dfrobot.com/

- [ ] DFRobot FireBeetle 2 ESP32-E — (url: to-verify)
- [ ] DFRobot FireBeetle 2 ESP32-S3 — (url: to-verify)
- [ ] DFRobot FireBeetle 2 ESP32-C6 — (url: to-verify)
- [ ] DFRobot Beetle ESP32-C3 — (url: to-verify)
- [ ] DFRobot Beetle ESP32-C6 — (url: to-verify)
- [ ] DFRobot ESP32-S3 AI Camera — (url: to-verify)

## Heltec

Official site: https://heltec.org/

- [ ] Heltec WiFi Kit 32 (ESP32) — (url: to-verify)
- [ ] Heltec WiFi LoRa 32 V3 (ESP32-S3) — (url: to-verify)
- [ ] Heltec Wireless Stick (ESP32) — (url: to-verify)
- [ ] Heltec Wireless Stick Lite (ESP32) — (url: to-verify)
- [ ] Heltec Vision Master E213/T190/etc. (ESP32-S3) — (url: to-verify)
- [ ] Heltec HTIT-WB32 (ESP32) — (url: to-verify)

## Olimex

Official site: https://www.olimex.com/

- [ ] Olimex ESP32-DevKit-LiPo — (url: to-verify)
- [ ] Olimex ESP32-PoE — (url: to-verify)
- [ ] Olimex ESP32-PoE-ISO — (url: to-verify)
- [ ] Olimex ESP32-EVB — (url: to-verify)
- [ ] Olimex ESP32-GATEWAY — (url: to-verify)
- [ ] Olimex ESP32-C3-DevKit-Lipo — (url: to-verify)
- [ ] Olimex ESP32-S3-DevKit-Lipo — (url: to-verify)

## Waveshare

Official site: https://www.waveshare.com/

- [ ] Waveshare ESP32-S3-DEV-KIT-N16R8 — (url: to-verify)
- [ ] Waveshare ESP32-C6-DEV-KIT-N8 — (url: to-verify)
- [ ] Waveshare ESP32-S3-Zero — (url: to-verify)
- [ ] Waveshare ESP32-C3-Zero — (url: to-verify)
- [ ] Waveshare ESP32-S3-Matrix — (url: to-verify)
- [ ] Waveshare ESP32-S3-Touch-LCD (various sizes) — (url: to-verify)

## WeAct

Official site: https://github.com/WeActStudio (vendor operates primarily via GitHub/AliExpress storefronts, no standalone corporate site)

- [ ] WeAct ESP32-C3 CoreBoard — (url: to-verify)
- [ ] WeAct ESP32-S3 CoreBoard — (url: to-verify)

## Banana Pi

Official site: http://www.banana-pi.org/

- [ ] BPI-Leaf-S3 (ESP32-S3) — (url: to-verify)
- [ ] BPI-Leaf (ESP32) — (url: to-verify)

## Other / To-Triage

Boards or vendors that need a first pass before they get their own section
(TinyML/AI-camera vendors, regional/AliExpress-only vendors, one-off dev
kits spotted in the wild, etc.). Add here first, promote to a vendor
section once a couple of boards are confirmed for that vendor.

- [ ] (none triaged yet)
