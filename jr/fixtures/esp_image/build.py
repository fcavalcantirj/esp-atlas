"""Builds the jr/esp_image.py test fixtures with the PINNED esptool's own image writer.

    jr/.venv/bin/python jr/fixtures/esp_image/build.py      # rewrites the *.bin next to this file

There is no ESP toolchain ELF on the box, so each image is an esptool ESP32FirmwareImage subclass
given ELF-like sections and saved by esptool (the same save() `elf2image` ends in): header,
segments, flash-alignment padding, checksum and appended SHA-256 are all esptool's. The broken
variants are then edited byte-wise from those, re-sealing the SHA-256 wherever a test means ONE
defect. test_esp_image.py rebuilds everything and compares it with the committed files, so the
fixtures can never drift from what the pinned parser writes. Deterministic: no clock, no randomness.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from esptool.bin_image import ELFSection, ESP32FirmwareImage, ESP32S3FirmwareImage

HERE = Path(__file__).resolve().parent
PARTITION_TABLE_OFFSET = 0x8000     # ESP-IDF's default CONFIG_PARTITION_TABLE_OFFSET
APP_OFFSET = 0x10000                # the factory app in ESP-IDF's default partition table


def _image(cls, sections, entry=0x40375000) -> bytes:
    img = cls()
    img.entrypoint = entry
    img.segments = [ELFSection(name.encode(), addr, data, 0) for name, addr, data in sections]
    return img.save(None)


def _words(tag: bytes, n: int) -> bytes:
    """n 4-byte words that do not XOR to zero, so a checksum is never the bare 0xEF seed."""
    return b"".join(tag[:2] + i.to_bytes(2, "little") for i in range(n))


def _reseal(data: bytes) -> bytes:
    """`data` with its appended SHA-256 recomputed: the edit before it stays the only defect."""
    return data[:-32] + hashlib.sha256(data[:-32]).digest()


def _segment_offsets(data: bytes) -> list[int]:
    off, offs = 24, []
    for _ in range(data[1]):
        offs.append(off)
        off += 8 + int.from_bytes(data[off + 4:off + 8], "little")
    return offs


def _patched(data: bytes, offset: int, value: int) -> bytes:
    return data[:offset] + bytes([value]) + data[offset + 1:]


def _flash(*parts: tuple[int, bytes]) -> bytes:
    """A merged flash image (what `esptool merge-bin` writes): each part at its offset, 0xFF between."""
    out = bytearray(b"\xff" * max(off + len(blob) for off, blob in parts))
    for off, blob in parts:
        out[off:off + len(blob)] = blob
    return bytes(out)


def _partition_table() -> bytes:
    """One esp_partition_info_t entry (magic 0xAA50, app/factory at APP_OFFSET), 0xFF after it."""
    entry = (b"\xaa\x50\x00\x00" + APP_OFFSET.to_bytes(4, "little") + (0x100000).to_bytes(4, "little")
             + b"factory".ljust(16, b"\x00") + bytes(4))
    return entry + b"\xff" * (0xC00 - len(entry))


def build_all() -> dict[str, bytes]:
    app = _image(ESP32S3FirmwareImage, [(".dram0.data", 0x3FC90000, _words(b"DR", 15)),
                                        (".iram0.text", 0x40378000, _words(b"IR", 7))])
    second = _segment_offsets(app)[1]
    s3_boot = _image(ESP32S3FirmwareImage, [(".dram0.bootdesc", 0x3FCD8000, _words(b"BD", 7)),
                                            (".iram_loader.text", 0x403C8000, _words(b"BL", 5))], entry=0x403C8000)
    esp32_boot = _image(ESP32FirmwareImage, [(".dram0.bootdesc", 0x3FFF0000, _words(b"BD", 7)),
                                             (".iram_loader.text", 0x40078000, _words(b"BL", 5))], entry=0x40078000)
    esp32_app = _image(ESP32FirmwareImage, [(".dram0.data", 0x3FFB0000, _words(b"DR", 15)),
                                            (".iram0.text", 0x40080000, _words(b"IR", 7))], entry=0x40080000)
    checksum_at = len(app) - 33
    return {
        "app_esp32s3.bin": app,
        "zero_length_segment.bin": _image(ESP32S3FirmwareImage, [(".dram0.data", 0x3FC90000, _words(b"DR", 15)),
                                                                 (".dram0.empty", 0x3FC90100, b""),
                                                                 (".iram0.text", 0x40378000, _words(b"IR", 7))]),
        # a flash-mapped .rodata forces esptool to insert its own load-address-0 padding segment
        "padding_segment.bin": _image(ESP32S3FirmwareImage, [(".flash.rodata", 0x3C000040, _words(b"RO", 15))]),
        "corrupt_after_first_segment.bin": _reseal(_patched(app, second + 8 + 5, app[second + 8 + 5] ^ 0x40)),
        "truncated.bin": app[:second + 8 + 12],
        "bad_checksum.bin": _reseal(_patched(app, checksum_at, app[checksum_at] ^ 0x01)),
        "bad_sha256.bin": _patched(app, len(app) - 1, app[-1] ^ 0x01),
        "unknown_chip.bin": _reseal(app[:12] + (0x0042).to_bytes(2, "little") + app[14:]),
        "merged_bootloader_0x0.bin": _flash((0, s3_boot), (PARTITION_TABLE_OFFSET, _partition_table()), (APP_OFFSET, app)),
        "merged_bootloader_0x1000.bin": _flash((0x1000, esp32_boot), (PARTITION_TABLE_OFFSET, _partition_table()),
                                               (APP_OFFSET, esp32_app)),
        "not_esp.bin": b"\x7fELF\x01\x01\x01\x00" + bytes(8) + b"#!/bin/sh\necho not an ESP image\n",
    }


def main() -> int:
    for name, data in build_all().items():
        (HERE / name).write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
