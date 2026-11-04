# Real released ESP image — a test fixture, never flashed

`esp32-wifi-penetration-tool-v1.0.bin` is a byte-for-byte copy of a public GitHub release asset,
committed so jr/test_esp_image.py checks the validator against an image built by ESP-IDF, not by
the pinned esptool writer that produced the other fixtures (../build.py). Tests read it offline.

| | |
|---|---|
| Project | [risinek/esp32-wifi-penetration-tool](https://github.com/risinek/esp32-wifi-penetration-tool) |
| Release tag | `v1.0` (tag commit `28a5b43165a968b1da1a92721b32d7bfd34be985`, published 2021-05-05) |
| Source URL | https://github.com/risinek/esp32-wifi-penetration-tool/releases/download/v1.0/esp32-wifi-penetration-tool.bin |
| License | MIT (project license, reproduced below); the image also links ESP-IDF, Apache-2.0 |
| Size | 723248 bytes |
| sha256 | `4b02feedb8aabd4c090901053b3894274eda28a97c9d9cb7cb5dcf44b9755a29` |
| What it is | an ESP32 ESP-IDF app image (header magic 0xE9, chip id 0x0000, 6 segments, SHA-256 appended), the app partition alone: the release ships bootloader and partition table as separate assets |

Downloaded 2026-11-04 with `gh release download v1.0 -R risinek/esp32-wifi-penetration-tool
-p esp32-wifi-penetration-tool.bin`; renamed only to carry the tag.

## License of the image (from the project's LICENSE)

```
MIT License

Copyright (c) 2021 risinek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
