"""Tests for jr/data_snapshot.py — the daily data-quality TREND row (SPEC-data-trend.md).

TDD, no network. A tiny temp fixture data dir with coding-domain ESP32 records (real-shaped ids
like `m5stack-cardputer`, `esp32-c6-devkitc-1`, `bruce`, `esphome`; never lorem ipsum). The finite
numbers come from scripts/data_completion.compute_completion (reused, not reimplemented); this
module adds only the INFINITE-ground volume + coverage signals and the trend history.

Run: cd jr && PYTHONPATH=../apps/core/src python3 -m pytest test_data_snapshot.py -q
"""
from __future__ import annotations

import json

import data_snapshot

# --- fixtures -------------------------------------------------------------

# A board with the four First-Flash fields present (usb_serial, getting_started, download_mode,
# pinout via io.gpio_pins) and mapped by a recipe.
BOARD_FULL = """---
id: m5stack-cardputer
type: board
brand: m5stack
name: M5Stack Cardputer
soc: esp32-s3
form_factor: cardputer
dimensions_mm:
- 83.5
- 54.0
usb:
  connector: usb-c
io:
  gpio_pins:
  - 1
  - 2
download_mode:
  mode: auto
usb_serial: native-usb-serial-jtag
getting_started: https://docs.m5stack.com/en/core/Cardputer
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-09-01'
---

# M5Stack Cardputer
"""

# A board with only usb_serial present, also mapped by a recipe.
BOARD_PARTIAL = """---
id: esp32-c6-devkitc-1
type: board
brand: espressif
name: ESP32-C6-DevKitC-1
soc: esp32-c6
usb_serial: native-usb-serial-jtag
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-idf/esp32-c6-devkitc-1
  verified: '2026-09-01'
---

# ESP32-C6-DevKitC-1
"""

# A board no recipe maps -> counts toward boards_zero_firmware.
BOARD_BARE = """---
id: esp32-c5-devkitc-1
type: board
brand: espressif
name: ESP32-C5-DevKitC-1
soc: esp32-c5
sources:
- field: '*'
  url: https://docs.espressif.com/projects/esp-idf/esp32-c5-devkitc-1
  verified: '2026-09-01'
---

# ESP32-C5-DevKitC-1
"""

FW = """---
id: {id}
type: firmware
name: {id}
---

# {id}
"""

RECIPE = """---
board: {board}
firmware: {firmware}
status: unverified
---

# {board} + {firmware}
"""


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_fixture(root):
    """Two mapped boards + one unmapped, two firmware, three recipes.
    => firmware_count=2, recipe_count=3, compat_density=1.5, boards_with_firmware=2,
       boards_zero_firmware=1; board_fields: usb_serial 2, getting_started/download_mode/pinout 1."""
    _write(root, "data/boards/m5stack/m5stack-cardputer/board.md", BOARD_FULL)
    _write(root, "data/boards/espressif/esp32-c6-devkitc-1/board.md", BOARD_PARTIAL)
    _write(root, "data/boards/espressif/esp32-c5-devkitc-1/board.md", BOARD_BARE)
    _write(root, "data/firmware/bruce/firmware.md", FW.format(id="bruce"))
    _write(root, "data/firmware/esphome/firmware.md", FW.format(id="esphome"))
    _write(root, "data/recipes/m5stack-cardputer__bruce/recipe.md",
           RECIPE.format(board="m5stack-cardputer", firmware="bruce"))
    _write(root, "data/recipes/esp32-c6-devkitc-1__bruce/recipe.md",
           RECIPE.format(board="esp32-c6-devkitc-1", firmware="bruce"))
    _write(root, "data/recipes/esp32-c6-devkitc-1__esphome/recipe.md",
           RECIPE.format(board="esp32-c6-devkitc-1", firmware="esphome"))


# --- build_row ------------------------------------------------------------

def test_build_row_volumes_compat_and_zero_firmware(tmp_path):
    _build_fixture(tmp_path)
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-09")
    assert row["date"] == "2026-09-09"
    assert row["firmware_count"] == 2
    assert row["recipe_count"] == 3
    assert row["compat_density"] == 1.5           # 3 recipes / 2 firmware
    assert row["boards_with_firmware"] == 2       # m5stack-cardputer, esp32-c6-devkitc-1
    assert row["boards_zero_firmware"] == 1       # esp32-c5-devkitc-1 is unmapped
    # board_fields pulled straight from the gauge's per_field, not rescanned
    assert row["board_fields"]["usb_serial"]["count"] == 2
    assert row["board_fields"]["getting_started"]["count"] == 1
    assert row["board_fields"]["download_mode"]["count"] == 1
    assert row["board_fields"]["pinout"]["count"] == 1
    # finite numbers echo compute_completion (not recomputed here)
    assert isinstance(row["finite_overall_pct"], float)
    assert "top_gap" in row and "%" in row["top_gap"]


def test_compat_density_zero_when_no_firmware(tmp_path):
    _write(tmp_path, "data/boards/m5stack/m5stack-cardputer/board.md", BOARD_FULL)
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-09")
    assert row["firmware_count"] == 0
    assert row["compat_density"] == 0.0


# --- write_snapshot: idempotency + delta ----------------------------------

def test_write_snapshot_is_idempotent_by_date(tmp_path):
    _build_fixture(tmp_path)
    jsonl = tmp_path / "docs" / "telemetry" / "data-trend.jsonl"
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    first = jsonl.read_text(encoding="utf-8")
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    second = jsonl.read_text(encoding="utf-8")
    assert first == second                        # byte-identical: no spurious churn
    assert len(first.strip().splitlines()) == 1   # one row for the one date
    row = json.loads(first.strip())
    assert row["date"] == "2026-09-09"


def test_first_snapshot_reports_no_baseline(tmp_path):
    _build_fixture(tmp_path)
    row, delta = data_snapshot.write_snapshot(tmp_path, "2026-09-08")
    assert delta is None
    md = (tmp_path / "docs" / "telemetry" / "data-2026-09-08.md").read_text(encoding="utf-8")
    assert "first snapshot — no baseline" in md
    assert "FINITE-GROUND DATA-COMPLETION GAUGE" in md   # the reused compute_completion text


def test_second_date_appends_row_and_md_shows_delta(tmp_path):
    _build_fixture(tmp_path)
    data_snapshot.write_snapshot(tmp_path, "2026-09-08")   # baseline: 2 fw, 3 recipes, compat 1.5

    # a new firmware + recipe lands the next day: counts and compat move
    _write(tmp_path, "data/firmware/wled/firmware.md", FW.format(id="wled"))
    _write(tmp_path, "data/recipes/esp32-c6-devkitc-1__wled/recipe.md",
           RECIPE.format(board="esp32-c6-devkitc-1", firmware="wled"))

    row, delta = data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    assert row["firmware_count"] == 3 and row["recipe_count"] == 4
    assert row["compat_density"] == 1.33          # 4 / 3
    assert delta is not None
    assert delta["since"] == "2026-09-08"
    assert delta["firmware_count"] == 1
    assert delta["recipe_count"] == 1
    assert delta["compat_density"] == -0.17       # 1.33 - 1.5

    jsonl = (tmp_path / "docs" / "telemetry" / "data-trend.jsonl").read_text(encoding="utf-8")
    lines = jsonl.strip().splitlines()
    assert [json.loads(l)["date"] for l in lines] == ["2026-09-08", "2026-09-09"]   # sorted asc

    md = (tmp_path / "docs" / "telemetry" / "data-2026-09-09.md").read_text(encoding="utf-8")
    assert "## Δ since 2026-09-08" in md
    assert "firmware_count: 3 (+1)" in md
    assert "recipe_count: 4 (+1)" in md
    assert "compat_density: 1.33 (-0.17)" in md


def test_jsonl_lines_are_compact_json(tmp_path):
    _build_fixture(tmp_path)
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    line = (tmp_path / "docs" / "telemetry" / "data-trend.jsonl").read_text(encoding="utf-8").strip()
    assert ", " not in line and '": ' not in line   # compact separators, no whitespace


# --- CLI ------------------------------------------------------------------

def test_cli_main_writes_both_files(tmp_path):
    _build_fixture(tmp_path)
    rc = data_snapshot.main(["--repo-root", str(tmp_path), "--date", "2026-09-09"])
    assert rc == 0
    assert (tmp_path / "docs" / "telemetry" / "data-trend.jsonl").exists()
    assert (tmp_path / "docs" / "telemetry" / "data-2026-09-09.md").exists()
