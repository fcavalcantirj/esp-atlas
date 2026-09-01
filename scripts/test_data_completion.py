"""Tests for scripts/data_completion.py -- the finite-ground completion gauge.

TDD, no network. Uses a small temp fixture data dir with coding-domain ESP32
example records (never lorem ipsum). Mirrors scripts/test_boot_coverage.py's
tmp_path fixture-writing convention.

Run: python3 -m pytest scripts/test_data_completion.py -q
"""
from __future__ import annotations

import data_completion

# --- fixtures -------------------------------------------------------------

# A board with EVERY usefulness field present (incl. getting_started, the
# field that does not exist in the real dataset yet) -> should score 100%.
BOARD_COMPLETE_MD = """---
id: esp32-c5-devkitc-1
type: board
brand: espressif
name: ESP32-C5-DevKitC-1
soc: esp32-c5
form_factor: devkitc
dimensions_mm:
- 25.4
- 63.5
usb:
  connector: usb-c
io:
  gpio_pins:
  - 0
  - 1
  - 2
download_mode:
  mode: auto
usb_serial: native-usb-serial-jtag
getting_started: https://docs.espressif.com/esp32-c5-devkitc-1
sources:
- field: '*'
  url: https://docs.espressif.com/esp32-c5-devkitc-1
  verified: '2026-09-01'
---

# ESP32-C5-DevKitC-1
"""

# A board missing download_mode AND pinout (io.gpio_pins) -> lower score, and
# those two fields must show up on the gaps worklist.
BOARD_GAPPY_MD = """---
id: adafruit-qtpy-esp32-s3
type: board
brand: adafruit
name: Adafruit QT Py ESP32-S3
soc: esp32-s3
form_factor: qtpy
dimensions_mm:
- 22.0
- 17.8
usb:
  connector: usb-c
usb_serial: native-usb-serial-jtag
sources:
- field: '*'
  url: https://learn.adafruit.com/adafruit-qt-py-esp32-s3
  verified: '2026-09-01'
---

# Adafruit QT Py ESP32-S3
"""

SOC_COMPLETE_MD = """---
id: esp32-s3
type: soc
vendor: espressif
name: ESP32-S3
cpu:
  arch: xtensa-lx7
  cores: 2
  max_mhz: 240
memory:
  sram_kb: 512
radios:
  wifi:
    standard: wifi-4
    bands_ghz:
    - 2.4
  bluetooth:
    le: '5.0'
drive:
  gpio_pads_total: 45
usb:
  native: true
sources:
- field: '*'
  url: https://docs.espressif.com/esp32-s3-datasheet
  verified: '2026-09-01'
---

# ESP32-S3
"""

MODULE_COMPLETE_MD = """---
id: esp32-s3-wroom-1
type: module
vendor: espressif
name: ESP32-S3-WROOM-1
soc: esp32-s3
flash_mb: 8
psram_mb: 8
antenna: pcb
certifications:
- fcc
- ce
sources:
- field: '*'
  url: https://docs.espressif.com/esp32-s3-wroom-1-datasheet
  verified: '2026-09-01'
---

# ESP32-S3-WROOM-1
"""

BRAND_COMPLETE_MD = """---
id: espressif
type: brand
name: Espressif Systems
url: https://www.espressif.com
sources:
- field: '*'
  url: https://www.espressif.com
  verified: '2026-09-01'
---

# Espressif Systems
"""


def _write(data_root, rel, text):
    p = data_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _write_board(data_root, brand, board_id, text):
    _write(data_root, f"boards/{brand}/{board_id}/board.md", text)


# --- tests ----------------------------------------------------------------

def test_fully_complete_board_scores_100(tmp_path):
    _write_board(tmp_path, "espressif", "esp32-c5-devkitc-1", BOARD_COMPLETE_MD)
    report = data_completion.compute_completion(tmp_path)
    boards = report["entities"]["boards"]
    assert boards["records"] == 1
    assert boards["pct"] == 100.0
    # every usefulness field at 100%
    for field, stats in boards["per_field"].items():
        assert stats["pct"] == 100.0, field


def test_gappy_board_scores_lower_and_lists_gaps(tmp_path):
    _write_board(tmp_path, "espressif", "esp32-c5-devkitc-1", BOARD_COMPLETE_MD)
    _write_board(tmp_path, "adafruit", "adafruit-qtpy-esp32-s3", BOARD_GAPPY_MD)
    report = data_completion.compute_completion(tmp_path)
    boards = report["entities"]["boards"]
    assert boards["records"] == 2
    assert boards["pct"] < 100.0
    # download_mode: only 1 of 2 boards has it; pinout: only 1 of 2.
    assert boards["per_field"]["download_mode"]["count"] == 1
    assert boards["per_field"]["pinout"]["count"] == 1
    # getting_started: neither board when only gappy? complete has it -> 1/2.
    # gaps worklist surfaces the lowest-% fields, incl. download_mode & pinout.
    gap_fields = {(g["entity"], g["field"]) for g in report["gaps"]}
    assert ("boards", "download_mode") in gap_fields
    assert ("boards", "pinout") in gap_fields


def test_overall_is_board_weighted(tmp_path):
    # Only a fully-complete board exists; the other three entity types are
    # empty (0 records -> 0%). With boards weighted 0.5 of the total weight,
    # the overall finite-completion must equal boards_weight/total_weight * 100.
    _write_board(tmp_path, "espressif", "esp32-c5-devkitc-1", BOARD_COMPLETE_MD)
    report = data_completion.compute_completion(tmp_path)
    assert report["entities"]["boards"]["pct"] == 100.0
    w = data_completion.WEIGHTS
    expected = w["boards"] / sum(w.values()) * 100.0
    assert abs(report["overall_pct"] - expected) < 1e-9
    # boards dominate: overall must exceed each of the other weights' share
    assert report["overall_pct"] > 0.0


def test_all_entity_types_fully_complete_scores_100(tmp_path):
    _write_board(tmp_path, "espressif", "esp32-c5-devkitc-1", BOARD_COMPLETE_MD)
    _write(tmp_path, "socs/esp32-s3/chip.md", SOC_COMPLETE_MD)
    _write(tmp_path, "modules/esp32-s3-wroom-1/module.md", MODULE_COMPLETE_MD)
    _write(tmp_path, "brands/espressif/brand.md", BRAND_COMPLETE_MD)
    report = data_completion.compute_completion(tmp_path)
    for name in ("boards", "socs", "modules", "brands"):
        assert report["entities"][name]["pct"] == 100.0, name
    assert abs(report["overall_pct"] - 100.0) < 1e-9


def test_empty_data_dir_does_not_crash(tmp_path):
    report = data_completion.compute_completion(tmp_path)
    for name in ("boards", "socs", "modules", "brands"):
        assert report["entities"][name]["records"] == 0
        assert report["entities"][name]["pct"] == 0.0
    assert report["overall_pct"] == 0.0


def test_native_usb_false_counts_as_present(tmp_path):
    # A SoC with usb.native: false has ANSWERED the native-usb question -> present.
    soc_no_native = SOC_COMPLETE_MD.replace("usb:\n  native: true", "usb:\n  native: false")
    _write(tmp_path, "socs/esp32/chip.md", soc_no_native)
    report = data_completion.compute_completion(tmp_path)
    assert report["entities"]["socs"]["per_field"]["native_usb"]["count"] == 1


def test_cli_main_runs_and_prints_gauge(tmp_path, capsys):
    _write_board(tmp_path, "espressif", "esp32-c5-devkitc-1", BOARD_COMPLETE_MD)
    exit_code = data_completion.main(["--data-dir", str(tmp_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OVERALL FINITE-COMPLETION" in out
    assert "boards" in out
    assert "download_mode" in out
