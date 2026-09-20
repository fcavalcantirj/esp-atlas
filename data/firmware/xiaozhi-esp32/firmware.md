---
id: xiaozhi-esp32
type: firmware
name: XiaoZhi ESP32
url: https://github.com/78/xiaozhi-esp32
category: multi
maintainer: '78'
license: MIT
socs:
- esp32
- esp32-c3
- esp32-c5
- esp32-c6
- esp32-p4
- esp32-s3
distribution:
- releases
capabilities:
- wifi
- display
requires:
- capability: wifi
  why: connects to the xiaozhi.me backend (or a self-hosted one) for the LLM/ASR/TTS
    pipeline
  board_signal: radio-wifi
popularity:
  stars: 30089
  forks: 7003
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/78/xiaozhi-esp32
  verified: '2026-08-26'
- field: license
  url: https://raw.githubusercontent.com/78/xiaozhi-esp32/main/LICENSE
  verified: '2026-08-26'
- field: socs
  url: https://github.com/78/xiaozhi-esp32#readme
  verified: '2026-08-26'
- field: popularity
  url: https://github.com/78/xiaozhi-esp32
  verified: '2026-09-01'
- field: socs
  url: https://github.com/78/xiaozhi-esp32/blob/main/sdkconfig.defaults.esp32c5
  verified: '2026-09-10'
- field: socs
  url: https://github.com/78/xiaozhi-esp32/blob/main/sdkconfig.defaults.esp32p4
  verified: '2026-09-10'
- field: summary
  url: https://github.com/78/xiaozhi-esp32
  verified: '2026-09-20'
summary: "XiaoZhi AI chatbot firmware for ESP32 devices enables voice\u2011interactive\
  \ AI chat using large language models (e.g., Qwen, DeepSeek) via the MCP protocol,\
  \ offering Wi\u2011Fi/4G networking, audio streaming, speaker recognition, display/emoji\
  \ support, and multi\u2011board compatibility."
readme_lang: en
readme_sha: 5a9acd964cbd9db5c59c70cff989b1e211629cba251a7e526d8e63e3feefdc3a
---

# XiaoZhi ESP32

An MCP-based voice chatbot firmware: wake-word detection, streaming ASR/LLM/TTS over
WebSocket or MQTT+UDP, and device-side MCP for controlling peripherals (speaker, LED,
servo, GPIO). Ships 138 board directories / 171 release variants, including the M5Stack
CoreS3 used here.

Discovered via the Launcher/M5Burner catalog (`api.launcherhub.net/giveMeTheList`),
with-code gated on its GitHub repo per SPEC-discovery.md. `status: unverified` on the
linked recipe; trust-tier promotion is human-only.
