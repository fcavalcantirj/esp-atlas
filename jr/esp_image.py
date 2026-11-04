"""EspAtlas Jr — the offline ESP image validator (jr/esp_image.py).

device_evidence's release_bin probe used to call a release .bin an ESP image on its first 16 bytes
(magic 0xE9 + a chip id). Owner spec 2026-11-04: those bytes prove nothing. validate() takes the
whole asset and answers

  esp_target    a single ESP-IDF app/bootloader image for a chip the pinned parser knows, whose
                every declared segment was walked and whose checksum (and appended SHA-256, when
                the header says one is there) was RECOMPUTED here and matched the stored bytes.
  needs_review  anything else, with the reasons: no 0xE9 header at offset 0 (a merged flash image
                with the bootloader at 0x1000, a .uf2, an ELF, text), an unknown chip id, a
                bootloader + partition table + app merge, truncation, a checksum or digest
                mismatch, unexplained bytes after the image, or ANY parser exception.

esp_target is chip target plus integrity only: never authorship, never board compatibility. A
successful parse — or esptool's own verify() — never counts on its own; the parser is used to read
the structure, and this module re-derives every integrity fact from the raw bytes.

The parser is esptool's image module (`esptool.bin_image.LoadFirmwareImage`), pinned exactly in
jr/requirements-image.txt; a different installed version is a review, not a guess. Nothing here
opens a port or flashes: `import esptool` loads its serial/flashing modules as a side effect of the
package __init__, but only bin_image is ever called. Pure: bytes in, verdict out, no I/O.
"""
from __future__ import annotations

import hashlib
import struct

ESP_TARGET = "esp_target"
NEEDS_REVIEW = "needs_review"
PINNED_ESPTOOL = "5.6.0"        # keep in step with jr/requirements-image.txt

# ESP-IDF components/bootloader_support/include/esp_app_format.h: esp_image_header_t is 24 bytes —
# magic, segment_count, spi_mode, spi_speed/size, entry_addr, wp_pin, 3 drive bytes, chip_id (u16 LE
# at 12), min_chip_rev, min/max_chip_rev_full, 4 reserved, hash_appended (byte 23). Each segment is
# an 8-byte esp_image_segment_header_t (load_addr, data_len) then its data. After the last segment,
# padding to the 16-byte boundary whose last byte is the checksum: 0xEF XOR every segment data byte.
# With hash_appended=1, a SHA-256 of everything before it follows.
IMAGE_MAGIC = 0xE9
HEADER_LEN = 24
SEGMENT_HEADER_LEN = 8
CHECKSUM_SEED = 0xEF
DIGEST_LEN = 32
FLASH_FILL = 0xFF               # erased flash: what `esptool merge-bin` and pad_to_size write
# Where a merged flash image keeps what a bare app image never has: the ESP32/S2 bootloader at
# 0x1000 (its offset 0 is then 0xFF), and ESP-IDF's default partition table (magic 0xAA50) at 0x8000.
MERGED_BOOTLOADER_OFFSET = 0x1000
PARTITION_TABLE_OFFSET = 0x8000
PARTITION_MAGIC = b"\xaa\x50"

# The esptool.bin_image classes LoadFirmwareImage dispatches to (all but ESP8266, whose images carry
# no chip id); each one's ROM_LOADER names the chip and its IMAGE_CHIP_ID.
_IMAGE_CLASSES = ("ESP32FirmwareImage", "ESP32S2FirmwareImage", "ESP32S3FirmwareImage", "ESP32C2FirmwareImage",
                  "ESP32C3FirmwareImage", "ESP32C5FirmwareImage", "ESP32C6FirmwareImage", "ESP32C61FirmwareImage",
                  "ESP32E22FirmwareImage", "ESP32H2FirmwareImage", "ESP32H21FirmwareImage", "ESP32H4FirmwareImage",
                  "ESP32P4FirmwareImage", "ESP32S31FirmwareImage")


class _Review(Exception):
    """A structural reason the bytes are not a single, intact ESP image."""


def validate(data: bytes) -> dict:
    """{"status": ESP_TARGET | NEEDS_REVIEW, "chip": "esp32s3" | None, "reasons": [str]} for the
    bytes of one release asset. chip is set only for ESP_TARGET."""
    if not isinstance(data, (bytes, bytearray)):
        return _review(f"not bytes ({type(data).__name__})")
    data = bytes(data)
    try:
        return _validate(data)
    except _Review as r:
        return _review(str(r))
    except Exception as e:  # noqa: BLE001 — owner rule: any parser exception is a review, never a pass
        return _review(f"parser error: {type(e).__name__}: {e}"[:300])


def _review(*reasons: str) -> dict:
    return {"status": NEEDS_REVIEW, "chip": None, "reasons": list(reasons)}


def _validate(data: bytes) -> dict:
    bin_image = _pinned_parser()
    if len(data) < HEADER_LEN or data[0] != IMAGE_MAGIC:
        raise _Review(_no_header(data))
    chip_id = int.from_bytes(data[12:14], "little")
    chip = chip_names(bin_image).get(chip_id)
    if chip is None:
        raise _Review(f"unknown chip id {chip_id:#06x} at offset 12")
    segments, end = _walk(data)
    checksum_at = end + (15 - end % 16)
    image_end = checksum_at + 1 + (DIGEST_LEN if _hash_appended(data) else 0)
    if image_end > len(data):
        raise _Review(f"truncated: the image needs {image_end} bytes, the asset has {len(data)}")
    _agrees_with_parser(bin_image.LoadFirmwareImage(chip, data), segments, chip_id)
    problems = _integrity(data, segments, checksum_at, image_end) + _trailing(data, image_end)
    if problems:
        return _review(*problems)
    digest = "SHA-256 verified" if _hash_appended(data) else "no SHA-256 appended"
    return {"status": ESP_TARGET, "chip": chip,
            "reasons": [f"{chip} image: {len(segments)} segments walked, checksum {data[checksum_at]:#04x} verified, {digest}"]}


def _pinned_parser():
    import esptool
    if esptool.__version__ != PINNED_ESPTOOL:
        raise _Review(f"esptool {esptool.__version__} installed, the validator is pinned to {PINNED_ESPTOOL}")
    from esptool import bin_image
    return bin_image


def chip_names(bin_image) -> dict[int, str]:
    """{chip id: LoadFirmwareImage's chip name ("esp32s3")} for every chip the pinned parser knows."""
    out = {}
    for name in _IMAGE_CLASSES:
        rom = getattr(bin_image, name).ROM_LOADER
        out[rom.IMAGE_CHIP_ID] = rom.CHIP_NAME.lower().replace("-", "")
    return out


def _no_header(data: bytes) -> str:
    if not data:
        return "empty asset"
    if len(data) > MERGED_BOOTLOADER_OFFSET and data[MERGED_BOOTLOADER_OFFSET] == IMAGE_MAGIC \
            and not data[:MERGED_BOOTLOADER_OFFSET].strip(bytes([FLASH_FILL])):
        return ("ESP image header not at offset 0 but at 0x1000 behind erased flash: "
                "a merged flash image (bootloader at 0x1000), not an app image")
    if len(data) < HEADER_LEN and data[0] == IMAGE_MAGIC:
        return f"truncated: {len(data)} bytes, an ESP image header alone is {HEADER_LEN}"
    return f"no ESP image header at offset 0 (byte 0 is {data[0]:#04x}, an ESP image starts {IMAGE_MAGIC:#04x})"


def _hash_appended(data: bytes) -> bool:
    return data[23] == 1


def _walk(data: bytes) -> tuple[list[tuple[int, int, int]], int]:
    """([(file offset, load addr, length)] for every segment the header declares, end offset),
    read straight from the bytes. A zero-length or load-address-0 (padding) segment is legal."""
    declared, off, segments = data[1], HEADER_LEN, []
    if declared == 0:
        raise _Review("the header declares no segments")
    for i in range(declared):
        if off + SEGMENT_HEADER_LEN > len(data):
            raise _Review(f"truncated: segment {i + 1} of {declared} has no header (offset {off:#x})")
        addr, size = struct.unpack_from("<II", data, off)
        if off + SEGMENT_HEADER_LEN + size > len(data):
            raise _Review(f"truncated: segment {i + 1} of {declared} declares {size} bytes at {off:#x}, "
                          f"{len(data) - off - SEGMENT_HEADER_LEN} remain")
        segments.append((off, addr, size))
        off += SEGMENT_HEADER_LEN + size
    return segments, off


def _agrees_with_parser(image, segments, chip_id: int) -> None:
    """The parser read the same structure this module walked — else neither reading is trusted."""
    parsed = [(s.file_offs, s.addr) for s in image.segments]
    if parsed != [(off, addr) for off, addr, _n in segments] or image.chip_id != chip_id:
        raise _Review("the parser and the raw segment walk disagree on the image structure")


def _integrity(data: bytes, segments, checksum_at: int, image_end: int) -> list[str]:
    problems = []
    checksum = CHECKSUM_SEED
    for off, _addr, size in segments:
        for b in data[off + SEGMENT_HEADER_LEN:off + SEGMENT_HEADER_LEN + size]:
            checksum ^= b
    if checksum != data[checksum_at]:
        problems.append(f"checksum mismatch: stored {data[checksum_at]:#04x}, computed {checksum:#04x} "
                        f"over {len(segments)} segments")
    if _hash_appended(data):
        stored = data[checksum_at + 1:image_end]
        computed = hashlib.sha256(data[:checksum_at + 1]).digest()
        if stored != computed:
            problems.append(f"SHA-256 mismatch: stored {stored.hex()}, computed {computed.hex()}")
    return problems


def _trailing(data: bytes, image_end: int) -> list[str]:
    """Erased-flash fill after the image is padding; anything else is not this image."""
    rest = data[image_end:]
    if not rest.strip(bytes([FLASH_FILL])):
        return []
    if data[PARTITION_TABLE_OFFSET:PARTITION_TABLE_OFFSET + 2] == PARTITION_MAGIC:
        return [f"merged flash image: a {data[1]}-segment image at 0x0, then a partition table at 0x8000 "
                f"(bootloader + partition table + app), not an app image"]
    return [f"{len(rest)} bytes after the image end ({image_end:#x}) that are not erased-flash fill "
            "(merged, signed or concatenated image?)"]
