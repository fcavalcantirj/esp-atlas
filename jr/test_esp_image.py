"""Tests for jr/esp_image.py — the offline ESP image validator behind device_evidence's release_bin.

Owner spec (2026-11-04): pinned esptool parser; every declared segment walked; padding (load
address 0) and zero-length segments legal; checksum and appended SHA-256 explicitly recomputed and
compared; unknown chip, merged/flash images, truncation, mismatches and any parser exception go to
review. A clean parse alone never passes. Fixtures in jr/fixtures/esp_image/ come from the pinned
esptool's own writer (build.py), and are checked against a fresh build below — except real/, a
released ESP-IDF image kept as published, so the validator is not only tested on its parser's kind."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

import esp_image

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "esp_image"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _build_module():
    spec = importlib.util.spec_from_file_location("esp_image_fixture_build", FIXTURES / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assert_review(res: dict, *words: str):
    assert res["status"] == esp_image.NEEDS_REVIEW and res["chip"] is None
    text = " ".join(res["reasons"]).lower()
    for w in words:
        assert w.lower() in text, (w, res["reasons"])


# --- the pinned parser and its fixtures ---------------------------------------------------------------

def test_the_parser_is_the_pinned_esptool():
    import esptool
    assert esptool.__version__ == esp_image.PINNED_ESPTOOL == "5.6.0"
    req = (Path(__file__).resolve().parent / "requirements-image.txt").read_text()
    assert f"esptool=={esp_image.PINNED_ESPTOOL}" in req.split()


def test_committed_fixtures_are_what_the_pinned_esptool_writes():
    built = _build_module().build_all()
    assert sorted(built) == sorted(p.name for p in FIXTURES.glob("*.bin"))
    for name, data in built.items():
        assert fixture(name) == data, name


def test_the_checksum_seed_is_esptool_s():
    from esptool.loader import ESPLoader
    assert esp_image.CHECKSUM_SEED == ESPLoader.ESP_CHECKSUM_MAGIC


# --- esp_target: chip target + integrity ----------------------------------------------------------------

def test_a_valid_esp32s3_app_image_is_an_esp_target():
    res = esp_image.validate(fixture("app_esp32s3.bin"))
    assert res["status"] == esp_image.ESP_TARGET and res["chip"] == "esp32s3"
    text = " ".join(res["reasons"])
    assert "2 segments" in text and "checksum" in text and "SHA-256" in text


def test_a_zero_length_segment_is_legal():
    res = esp_image.validate(fixture("zero_length_segment.bin"))
    assert res["status"] == esp_image.ESP_TARGET and res["chip"] == "esp32s3"
    assert "3 segments" in " ".join(res["reasons"])


def test_a_padding_segment_at_address_zero_is_legal():
    data = fixture("padding_segment.bin")
    assert int.from_bytes(data[24:28], "little") == 0             # the first segment loads at 0: padding
    res = esp_image.validate(data)
    assert res["status"] == esp_image.ESP_TARGET and res["chip"] == "esp32s3"


def test_bytearray_input_is_accepted():
    assert esp_image.validate(bytearray(fixture("app_esp32s3.bin")))["status"] == esp_image.ESP_TARGET


def test_an_image_without_an_appended_digest_passes_on_its_checksum():
    """hash_appended=0 (header byte 23): no SHA-256 to compare; the checksum still must match."""
    from esptool.bin_image import ELFSection, ESP32S3FirmwareImage
    img = ESP32S3FirmwareImage()
    img.append_digest = False
    img.segments = [ELFSection(b".dram0.data", 0x3FC90000, b"ABCD" * 4, 0)]
    data = img.save(None)
    res = esp_image.validate(data)
    assert res["status"] == esp_image.ESP_TARGET and "no SHA-256 appended" in " ".join(res["reasons"])
    assert_review(esp_image.validate(data[:-1] + bytes([data[-1] ^ 0x10])), "checksum")


# --- needs_review: integrity ------------------------------------------------------------------------

def test_corruption_after_the_first_segment_needs_review():
    """The defect sits in segment 2's data, the stored checksum is untouched and the SHA-256 is
    re-sealed: only a checksum recomputed over EVERY segment catches it."""
    assert_review(esp_image.validate(fixture("corrupt_after_first_segment.bin")), "checksum mismatch")


def test_a_truncated_image_needs_review():
    assert_review(esp_image.validate(fixture("truncated.bin")), "truncated")


@pytest.mark.parametrize("cut", [1, 10, 32, 33])
def test_an_image_cut_in_its_trailer_needs_review(cut):
    assert_review(esp_image.validate(fixture("app_esp32s3.bin")[:-cut]), "truncated")


def test_a_wrong_checksum_byte_needs_review():
    assert_review(esp_image.validate(fixture("bad_checksum.bin")), "checksum mismatch")


def test_a_wrong_appended_sha256_needs_review():
    assert_review(esp_image.validate(fixture("bad_sha256.bin")), "sha-256 mismatch")


@pytest.mark.parametrize("name,why", [("bad_checksum.bin", "checksum mismatch"), ("bad_sha256.bin", "sha-256 mismatch")])
def test_a_clean_parse_alone_never_passes(monkeypatch, name, why):
    """The parser loads these without raising (its verify() only counts segments). Even when its
    own reading is made to say all is well — stored checksum = computed, stored digest = computed —
    the bytes this module recomputes decide."""
    from esptool import bin_image
    real = bin_image.LoadFirmwareImage
    loaded = []

    def vouching(chip, image_data):
        img = real(chip, image_data)
        img.checksum = img.calculate_checksum()
        img.stored_digest = img.calc_digest
        img.verify()
        loaded.append(img)
        return img
    monkeypatch.setattr(bin_image, "LoadFirmwareImage", vouching)
    assert_review(esp_image.validate(fixture(name)), why)
    assert loaded, "the parser must have run and succeeded"


# --- needs_review: not a (single, known) ESP app image ---------------------------------------------------

def test_an_unknown_chip_id_needs_review():
    assert_review(esp_image.validate(fixture("unknown_chip.bin")), "unknown chip id 0x0042")


def test_a_merged_image_with_the_bootloader_at_0x0_needs_review():
    assert_review(esp_image.validate(fixture("merged_bootloader_0x0.bin")), "merged", "partition table at 0x8000")


def test_a_merged_image_with_the_bootloader_at_0x1000_needs_review():
    assert_review(esp_image.validate(fixture("merged_bootloader_0x1000.bin")), "not at offset 0", "0x1000")


def test_unexplained_bytes_after_the_image_need_review():
    assert_review(esp_image.validate(fixture("app_esp32s3.bin") + b"\x00extra"), "after the image")


def test_0xff_fill_after_the_image_is_flash_padding():
    assert esp_image.validate(fixture("app_esp32s3.bin") + b"\xff" * 64)["status"] == esp_image.ESP_TARGET


@pytest.mark.parametrize("data", [fixture("not_esp.bin"), b"", b"\xe9", b"hello world" * 10, bytes(4096)])
def test_non_esp_bytes_need_review(data):
    assert_review(esp_image.validate(data))


def test_non_bytes_need_review_and_are_never_read_as_a_path():
    """esptool's get_bytes() opens a str as a FILE PATH: validate() must never hand it one."""
    assert_review(esp_image.validate("/etc/passwd"), "not bytes")
    assert_review(esp_image.validate(None), "not bytes")


def test_a_header_with_no_segments_needs_review():
    data = bytearray(fixture("app_esp32s3.bin")[:24])
    data[1] = 0
    data += bytes(7) + bytes([esp_image.CHECKSUM_SEED])
    data += hashlib.sha256(bytes(data)).digest()
    assert_review(esp_image.validate(bytes(data)), "no segments")


def test_a_header_declaring_fewer_segments_than_the_image_has_needs_review():
    data = fixture("zero_length_segment.bin")
    fewer = bytes([data[0], data[1] - 1]) + data[2:]          # the header now hides the last segment
    assert_review(esp_image.validate(fewer), "checksum mismatch", "after the image end")


def _one_segment_image(payload: bytes) -> bytes:
    """A hand-built S3 image with one segment of len(payload) bytes, checksum and SHA-256 correct."""
    data = bytearray(fixture("app_esp32s3.bin")[:24])
    data[1] = 1
    data += (0x3FC90000).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload
    checksum = esp_image.CHECKSUM_SEED
    for b in payload:
        checksum ^= b
    data += bytes(15 - len(data) % 16) + bytes([checksum])
    return bytes(data) + hashlib.sha256(bytes(data)).digest()


def test_the_hand_built_one_segment_image_is_valid():
    assert esp_image.validate(_one_segment_image(b"ABCDEFGH"))["status"] == esp_image.ESP_TARGET


def test_a_segment_length_that_is_not_a_multiple_of_4_needs_review():
    """esptool's writer refuses such a length and ESP-IDF checksums words: the parser's silent zero
    padding must not let an otherwise self-consistent image through."""
    assert_review(esp_image.validate(_one_segment_image(b"ABCDE")), "multiple of 4")


def test_any_parser_exception_needs_review(monkeypatch):
    import struct

    from esptool import bin_image

    def boom(chip, image_data):
        raise struct.error("unpack requires a buffer of 8 bytes")
    monkeypatch.setattr(bin_image, "LoadFirmwareImage", boom)
    assert_review(esp_image.validate(fixture("app_esp32s3.bin")), "parser", "unpack")


def test_an_invalid_hash_appended_flag_needs_review():
    data = bytearray(fixture("app_esp32s3.bin"))
    data[23] = 7
    assert_review(esp_image.validate(bytes(data)), "parser")


def test_a_different_esptool_version_needs_review(monkeypatch):
    import esptool
    monkeypatch.setattr(esptool, "__version__", "5.7.0")
    assert_review(esp_image.validate(fixture("app_esp32s3.bin")), "5.7.0", "5.6.0")


def test_validate_never_opens_a_serial_port_or_connects_a_loader(monkeypatch):
    """Only bin_image is CALLED. (`import esptool` loads its cmds/serial modules as a side effect of
    the package __init__; nothing in them runs.) Any port open or chip connect would raise here."""
    import serial
    from esptool import cmds, loader

    def forbidden(*a, **k):
        raise AssertionError("serial / flashing code reached")
    monkeypatch.setattr(serial.Serial, "__init__", forbidden)
    monkeypatch.setattr(loader.ESPLoader, "__init__", forbidden)
    monkeypatch.setattr(cmds, "detect_chip", forbidden)
    assert esp_image.validate(fixture("app_esp32s3.bin"))["status"] == esp_image.ESP_TARGET


def test_an_image_cut_inside_a_segment_header_needs_review():
    data = fixture("app_esp32s3.bin")
    second = 24 + 8 + int.from_bytes(data[28:32], "little")
    assert_review(esp_image.validate(data[:second + 4]), "truncated", "segment 2 of 2 has no header")


def test_a_parser_reading_that_disagrees_with_the_raw_walk_needs_review(monkeypatch):
    from esptool import bin_image
    real = bin_image.LoadFirmwareImage

    def skewed(chip, image_data):
        img = real(chip, image_data)
        img.segments = img.segments[:1]
        return img
    monkeypatch.setattr(bin_image, "LoadFirmwareImage", skewed)
    assert_review(esp_image.validate(fixture("app_esp32s3.bin")), "disagree")


# --- owner additions 2026-11-04 ---------------------------------------------------------------------------

REAL = FIXTURES / "real"
REAL_APP = "esp32-wifi-penetration-tool-v1.0.bin"
REAL_APP_SHA256 = "4b02feedb8aabd4c090901053b3894274eda28a97c9d9cb7cb5dcf44b9755a29"


def _segments(data: bytes) -> list[tuple[int, int]]:
    """[(data offset, length)] per declared segment, walked here independently of esp_image."""
    off, out = 24, []
    for _ in range(data[1]):
        size = int.from_bytes(data[off + 4:off + 8], "little")
        out.append((off + 8, size))
        off += 8 + size
    return out


def _xor_checksum(data: bytes) -> tuple[int, int]:
    """(stored checksum byte, 0xEF XOR every segment data byte) — the checksum ALONE."""
    computed, end = esp_image.CHECKSUM_SEED, 24
    for off, size in _segments(data):
        for b in data[off:off + size]:
            computed ^= b
        end = off + size
    return data[end + (15 - end % 16)], computed


def test_the_real_image_is_the_released_asset_its_readme_names():
    data = (REAL / REAL_APP).read_bytes()
    assert hashlib.sha256(data).hexdigest() == REAL_APP_SHA256
    readme = (REAL / "README.md").read_text()
    for fact in (REAL_APP_SHA256, "releases/download/v1.0/esp32-wifi-penetration-tool.bin", "MIT"):
        assert fact in readme, fact


def test_a_real_released_esp32_app_image_is_an_esp_target():
    """Built by ESP-IDF (not by the esptool writer behind the other fixtures) and published as a
    GitHub release asset: the validator must accept a real-world image, not only its own kind."""
    res = esp_image.validate((REAL / REAL_APP).read_bytes())
    assert res["status"] == esp_image.ESP_TARGET and res["chip"] == "esp32"
    assert "6 segments" in " ".join(res["reasons"]) and "SHA-256 verified" in " ".join(res["reasons"])


def test_the_real_image_corrupted_in_its_last_segment_needs_review():
    data = bytearray((REAL / REAL_APP).read_bytes())
    off, size = _segments(bytes(data))[-1]
    data[off + size // 2] ^= 0x01
    data[-32:] = hashlib.sha256(bytes(data[:-32])).digest()       # re-sealed: the checksum must catch it
    assert_review(esp_image.validate(bytes(data)), "checksum mismatch")


def test_the_real_image_truncated_inside_its_last_segment_needs_review():
    data = (REAL / REAL_APP).read_bytes()
    off, size = _segments(data)[-1]
    assert_review(esp_image.validate(data[:off + size // 2]), "truncated", "segment 6 of 6")


@pytest.mark.parametrize("name,digest", [("app_esp32s3.bin", True), ("app_esp32s3_no_sha256.bin", False)])
def test_images_with_and_without_the_appended_sha256_are_esp_targets(name, digest):
    data = fixture(name)
    assert data[23] == int(digest)                                # header hash_appended flag
    res = esp_image.validate(data)
    assert res["status"] == esp_image.ESP_TARGET and res["chip"] == "esp32s3"
    assert ("SHA-256 verified" if digest else "no SHA-256 appended") in " ".join(res["reasons"])


def test_the_digest_and_no_digest_fixtures_differ_only_by_the_flag_and_the_digest():
    with_digest, without = fixture("app_esp32s3.bin"), fixture("app_esp32s3_no_sha256.bin")
    assert len(with_digest) == len(without) + 32
    assert with_digest[:23] + with_digest[24:-32] == without[:23] + without[24:]


def test_corruption_inside_the_last_segment_needs_review():
    data = fixture("corrupt_last_segment.bin")
    assert len(_segments(data)) == 4
    stored, computed = _xor_checksum(data)
    assert stored != computed
    assert_review(esp_image.validate(data), "checksum mismatch", "over 4 segments")


def test_truncation_inside_a_late_segment_needs_review():
    assert_review(esp_image.validate(fixture("truncated_late_segment.bin")), "truncated", "segment 4 of 4")


def test_a_mutation_that_keeps_the_xor_checksum_but_breaks_the_sha256_needs_review():
    """Two bytes of one segment flipped by the same mask cancel in the XOR checksum: only the
    recomputed SHA-256 can tell this image from the original."""
    data, original = fixture("xor_cancelling_pair.bin"), fixture("app_esp32s3.bin")
    assert data != original and len(data) == len(original)
    stored, computed = _xor_checksum(data)
    assert stored == computed == _xor_checksum(original)[0]       # the checksum alone still matches
    res = esp_image.validate(data)
    assert_review(res, "sha-256 mismatch")
    assert "checksum mismatch" not in " ".join(res["reasons"]).lower()
