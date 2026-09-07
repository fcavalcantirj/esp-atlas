"""Tests for scripts/build_board_universe.py — offline, on tmp_path fixtures; no network.

The only repo data read is data/socs/ (through esp_atlas_core.validate.known_ids) in one test
that pins the mcu → soc mapping to the catalogued soc ids.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_board_universe as bbu  # noqa: E402

BOARDS_TXT = """\
# comment line
menu.PartitionScheme=Partition Scheme

esp32s3.name=ESP32S3 Dev Module
esp32s3.menu.PartitionScheme.default=Default 4MB
esp32s3.build.mcu=esp32s3
esp32s3.build.variant=esp32s3
esp32s3.build.board=ESP32S3_DEV

m5stack_cardputer.name=M5Cardputer
m5stack_cardputer.build.mcu=esp32s3
m5stack_cardputer.build.variant=m5stack_cardputer
m5stack_cardputer.build.board=M5STACK_CARDPUTER

esp32_family.name=ESP32 Family Device
esp32_family.build.board=ESP32_FAMILY

weird.name=Chip From The Future
weird.build.mcu=esp32zz
"""

PIO_STAMPS3 = {"name": "M5Stack StampS3", "vendor": "M5Stack", "url": "https://docs.m5stack.com/en/core/StampS3",
               "build": {"mcu": "esp32s3", "variant": "m5stack_stamp_s3"}}
PIO_C61 = {"name": "ESP32-C61 DevKitC-1", "vendor": "Espressif", "build": {"mcu": "esp32c61", "variant": "esp32c61"}}
LAUNCHER = [{"name": "A", "category": "Cardputer", "esp": "s3"}, {"name": "B", "category": "cardputer", "esp": "S3"},
            {"name": "C", "category": "stickc", "esp": "32"}, {"name": "D", "category": "", "esp": "32"},
            {"name": "E", "category": "stickc", "esp": None}]
SOCS = {"esp32", "esp32-s3", "esp32-c61"}


@pytest.fixture
def fixtures(tmp_path):
    (tmp_path / "boards.txt").write_text(BOARDS_TXT)
    (tmp_path / "pio").mkdir()
    (tmp_path / "pio" / "m5stack-stamps3.json").write_text(json.dumps(PIO_STAMPS3))
    (tmp_path / "pio" / "esp32-c61-devkitc1.json").write_text(json.dumps(PIO_C61))
    (tmp_path / "launcher.json").write_text(json.dumps(LAUNCHER))
    (tmp_path / "refs.json").write_text(json.dumps({"arduino_sha": "a" * 40, "pio_sha": "b" * 40}))
    return tmp_path


def test_parse_boards_txt_reads_only_top_level_name_and_build_keys():
    boards = bbu.parse_boards_txt(BOARDS_TXT)
    assert set(boards) == {"esp32s3", "m5stack_cardputer", "esp32_family", "weird"}
    assert boards["m5stack_cardputer"] == {"name": "M5Cardputer", "line": 10, "mcu": "esp32s3",
                                           "variant": "m5stack_cardputer", "board_define": "M5STACK_CARDPUTER"}
    assert "menu" not in json.dumps(boards)
    assert boards["esp32_family"] == {"name": "ESP32 Family Device", "line": 15, "board_define": "ESP32_FAMILY"}


def test_soc_mapping_is_mechanical_but_gated_on_the_catalog():
    assert bbu.soc_for("esp32s3", SOCS) == "esp32-s3"
    assert bbu.soc_for("ESP32C61", SOCS) == "esp32-c61"
    assert bbu.soc_for("esp32c3", SOCS) is None          # mechanical map exists, soc not in this catalog
    assert bbu.soc_for("esp32zz", SOCS) is None          # unknown mcu
    assert bbu.soc_for(None, SOCS) is None


def test_soc_mapping_covers_every_mcu_the_real_catalog_knows():
    from esp_atlas_core.validate import known_ids
    real = known_ids()["soc"]
    for mcu, soc in bbu._MCU_TO_SOC.items():
        assert soc in real, f"{mcu} → {soc} is not a catalogued soc"


def test_build_universe_is_deterministic_and_cites_every_entry(fixtures):
    inputs = bbu.gather_offline(fixtures)
    u1 = bbu.build_universe(today="2026-09-07", known_socs=SOCS, **inputs)
    u2 = bbu.build_universe(today="2026-09-07", known_socs=SOCS, **inputs)
    assert u1 == u2
    keys = [b["key"] for b in u1["boards"]]
    assert keys == sorted(keys)
    assert keys == ["arduino-esp32:esp32_family", "arduino-esp32:esp32s3", "arduino-esp32:m5stack_cardputer",
                    "arduino-esp32:weird", "pioarduino:esp32-c61-devkitc1", "pioarduino:m5stack-stamps3"]
    card = next(b for b in u1["boards"] if b["key"] == "arduino-esp32:m5stack_cardputer")
    assert card["url"] == "https://github.com/espressif/arduino-esp32/blob/" + "a" * 40 + "/boards.txt#L10"
    assert card["soc"] == "esp32-s3" and card["verified"] == "2026-09-07" and card["board_define"] == "M5STACK_CARDPUTER"
    stamp = next(b for b in u1["boards"] if b["key"] == "pioarduino:m5stack-stamps3")
    assert stamp["url"] == "https://github.com/pioarduino/platform-espressif32/blob/" + "b" * 40 + "/boards/m5stack-stamps3.json"
    assert stamp["vendor"] == "M5Stack" and stamp["vendor_url"].startswith("https://docs.m5stack.com/")
    assert stamp["variant"] == "m5stack_stamp_s3" and stamp["soc"] == "esp32-s3"
    weird = next(b for b in u1["boards"] if b["id"] == "weird")
    assert weird["mcu"] == "esp32zz" and weird["soc"] is None
    family = next(b for b in u1["boards"] if b["id"] == "esp32_family")
    assert family["mcu"] is None and family["soc"] is None
    assert all("atlas_id" not in b for b in u1["boards"])            # resolution is not the artifact's job
    assert [s["count"] for s in u1["sources"]] == [4, 2, 5]
    assert u1["sources"][0]["ref"] == "a" * 40


def test_launcher_categories_are_lowercased_counted_and_chip_binned():
    cats = bbu.launcher_categories(LAUNCHER)
    assert cats == {"cardputer": {"count": 2, "esp": {"s3": 2}},
                    "stickc": {"count": 2, "esp": {"32": 1, "unknown": 1}}}


def test_main_offline_writes_the_artifact_with_a_trailing_newline(fixtures, tmp_path, capsys):
    out = tmp_path / "u.json"
    rc = bbu.main(["--offline", "--fixtures", str(fixtures), "--out", str(out), "--today", "2026-09-07"])
    assert rc == 0
    raw = out.read_text()
    assert raw.endswith("}\n")
    data = json.loads(raw)
    assert data["generated"] == "2026-09-07" and len(data["boards"]) == 6
    assert "wrote" in capsys.readouterr().out


def test_gather_live_pins_shas_and_walks_the_pio_listing():
    calls = []

    def fetch(url, timeout=60.0):
        calls.append(url)
        if url.endswith("/commits/master"):
            return json.dumps({"sha": "c" * 40}).encode()
        if url.endswith("/commits/develop"):
            return json.dumps({"sha": "d" * 40}).encode()
        if "/boards.txt" in url:
            assert "c" * 40 in url
            return BOARDS_TXT.encode()
        if "/contents/boards?ref=" in url:
            return json.dumps([{"name": "m5stack-stamps3.json"}, {"name": "README.md"}]).encode()
        if url.endswith("/boards/m5stack-stamps3.json"):
            assert "d" * 40 in url
            return json.dumps(PIO_STAMPS3).encode()
        if "launcherhub" in url:
            return json.dumps(LAUNCHER).encode()
        raise AssertionError(url)
    inputs = bbu.gather_live(fetch=fetch, log=lambda *a: None)
    assert inputs["arduino_sha"] == "c" * 40 and inputs["pio_sha"] == "d" * 40
    assert list(inputs["pio_boards"]) == ["m5stack-stamps3"]
    assert len(inputs["launcher"]) == 5
    assert not any(u.endswith("README.md") for u in calls)
