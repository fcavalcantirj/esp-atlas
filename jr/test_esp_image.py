"""Tests for jr/esp_image.py — the offline ESP image validator behind device_evidence's release_bin.

Owner spec (2026-11-04): pinned esptool parser; every declared segment walked; padding (load
address 0) and zero-length segments legal; checksum and appended SHA-256 explicitly recomputed and
compared; unknown chip, merged/flash images, truncation, mismatches and any parser exception go to
review. A clean parse alone never passes. Fixtures in jr/fixtures/esp_image/ come from the pinned
esptool's own writer (build.py), and are checked against a fresh build below."""
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
    """The defect sits in segment 2: a validator that stopped at segment 1 would pass it."""
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


def test_a_clean_parse_alone_never_passes(monkeypatch):
    """Even if the parser itself reported no problem, the explicit recomputation decides."""
    from esptool import bin_image
    data = fixture("bad_checksum.bin")
    real = bin_image.LoadFirmwareImage

    def lenient(chip, image_data):
        img = real(chip, image_data)
        img.verify = lambda: None
        return img
    monkeypatch.setattr(bin_image, "LoadFirmwareImage", lenient)
    assert_review(esp_image.validate(data), "checksum mismatch")


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


def test_more_segments_than_the_header_declares_is_trailing_data():
    data = fixture("zero_length_segment.bin")
    fewer = bytes([data[0], data[1] - 1]) + data[2:]          # the header now hides the last segment
    assert_review(esp_image.validate(fewer))


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
