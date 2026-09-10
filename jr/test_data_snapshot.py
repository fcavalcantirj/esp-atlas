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


# --- v2.a entity_fields: record every per-field metric --------------------

def test_entity_fields_covers_every_gauge_field(tmp_path):
    _build_fixture(tmp_path)
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-09")
    ef = row["entity_fields"]
    # every entity the gauge measures is present
    assert set(ef) == {"boards", "socs", "modules", "brands"}
    # boards carry all 8 fields, in FIELD_SPECS (report) order
    assert list(ef["boards"]) == [
        "download_mode", "usb_serial", "pinout", "dimensions_mm",
        "form_factor", "usb_connector", "getting_started", "images",
    ]
    assert len(ef["socs"]) == 5 and len(ef["modules"]) == 5 and len(ef["brands"]) == 1
    # each cell is a {count, pct} pulled straight from the gauge (not rescanned)
    assert set(ef["boards"]["pinout"]) == {"count", "pct"}
    assert ef["boards"]["usb_serial"]["count"] == 2
    assert ef["boards"]["pinout"]["count"] == 1        # io.gpio_pins only on m5stack-cardputer
    assert ef["boards"]["images"]["count"] == 0        # no board carries images yet -> floor


def test_board_fields_is_unchanged_and_a_subset_of_entity_fields(tmp_path):
    _build_fixture(tmp_path)
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-09")
    ef_boards = row["entity_fields"]["boards"]
    # board_fields (the 4 First-Flash keys) stay exactly as v1 — and are a subset of entity_fields
    for f in data_snapshot.BOARD_TREND_FIELDS:
        assert f in ef_boards
        assert row["board_fields"][f] == ef_boards[f]


def test_entity_fields_round_trips_through_the_jsonl_idempotently(tmp_path):
    _build_fixture(tmp_path)
    jsonl = tmp_path / "docs" / "telemetry" / "data-trend.jsonl"
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    first = jsonl.read_text(encoding="utf-8")
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    assert jsonl.read_text(encoding="utf-8") == first     # byte-identical: no churn from entity_fields
    row = json.loads(first.strip())
    assert row["entity_fields"]["boards"]["usb_serial"]["count"] == 2


# --- v2.a/v2.b back-compat: a row/history without entity_fields never crashes ----

def test_compute_delta_survives_a_legacy_prev_without_entity_fields(tmp_path):
    _build_fixture(tmp_path)
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-02")
    legacy_prev = {                                        # a v1 row: no entity_fields key
        "date": "2026-09-01", "finite_overall_pct": 40.0,
        "board_fields": {"usb_serial": {"count": 1, "pct": 5.0}},
        "firmware_count": 1, "recipe_count": 1, "compat_density": 1.0,
    }
    d = data_snapshot.compute_delta(row, legacy_prev)      # must not raise
    assert d is not None and "board_fields" in d
    assert d["board_fields"]["usb_serial"] == 2 - 1


# --- v2.b field_momentum: staleness verdict (pure, no clock) ---------------

def _mrow(date, count, pct=10.0, entity="boards", field="pinout"):
    """A synthetic trend row carrying one entity field's count (esp32 board field)."""
    return {"date": date, "board_fields": {},
            "entity_fields": {entity: {field: {"count": count, "pct": pct}}}}


def test_default_window_is_seven():
    assert data_snapshot.DEFAULT_WINDOW == 7


def test_field_momentum_improving_and_declining():
    up = [_mrow("2026-09-01", 15), _mrow("2026-09-02", 22), _mrow("2026-09-03", 35)]
    m = data_snapshot.field_momentum(up, window=2)
    assert m["boards.pinout"]["status"] == "improving"
    assert m["boards.pinout"]["delta_window"] == 20        # 35 - 15
    assert m["boards.pinout"]["since"] == "2026-09-01"
    down = [_mrow("2026-09-01", 20), _mrow("2026-09-02", 18), _mrow("2026-09-03", 15)]
    md = data_snapshot.field_momentum(down, window=2)
    assert md["boards.pinout"]["status"] == "declining"
    assert md["boards.pinout"]["delta_window"] == -5


def test_field_momentum_flat_when_history_shorter_than_window():
    # three equal snapshots but not yet a full window (window=3) -> too soon to judge -> flat
    flat = [_mrow("2026-09-01", 15), _mrow("2026-09-02", 15), _mrow("2026-09-03", 15)]
    v = data_snapshot.field_momentum(flat, window=3)["boards.pinout"]
    assert v["status"] == "flat" and v["delta_window"] == 0


def test_field_momentum_stale_across_a_full_window():
    # a field stuck across a full window of consecutive snapshots -> stale, not a bare 0-delta
    stale = [_mrow(f"2026-09-0{i}", 15) for i in (1, 2, 3, 4)]
    v = data_snapshot.field_momentum(stale, window=3)["boards.pinout"]
    assert v["status"] == "stale" and v["delta_window"] == 0
    assert v["since"] == "2026-09-01"


def test_field_momentum_uses_earliest_when_history_shorter_than_window():
    rows = [_mrow("2026-09-01", 10), _mrow("2026-09-02", 14)]   # only 2 rows, window 7
    m = data_snapshot.field_momentum(rows, window=7)
    assert m["boards.pinout"]["since"] == "2026-09-01"          # earliest available
    assert m["boards.pinout"]["status"] == "improving" and m["boards.pinout"]["delta_window"] == 4


def test_field_momentum_backcompat_history_without_entity_fields():
    legacy = {"date": "2026-09-01", "board_fields": {"pinout": {"count": 9, "pct": 10.0}}}  # no entity_fields
    cur = _mrow("2026-09-02", 15)
    m = data_snapshot.field_momentum([legacy, cur], window=7)   # must not crash
    assert "boards.pinout" in m
    assert m["boards.pinout"]["status"] in {"improving", "declining", "flat", "stale"}


def test_field_momentum_empty_history_is_empty():
    assert data_snapshot.field_momentum([]) == {}


# --- v2.c markdown: Field coverage section ---------------------------------

def test_write_snapshot_markdown_has_a_field_coverage_section(tmp_path):
    _build_fixture(tmp_path)
    data_snapshot.write_snapshot(tmp_path, "2026-09-09")
    md = (tmp_path / "docs" / "telemetry" / "data-2026-09-09.md").read_text(encoding="utf-8")
    assert "## Field coverage" in md
    assert "boards.pinout:" in md                              # the floor fields are surfaced
    assert md.index("## Δ") < md.index("## Field coverage")     # coverage comes AFTER the Δ block


def test_render_markdown_orders_worst_pct_first_and_marks_stale(tmp_path):
    _build_fixture(tmp_path)
    import data_completion
    gauge = data_completion.compute_completion(str(tmp_path / "data"))
    row = data_snapshot.build_row(tmp_path / "data", "2026-09-10")
    momentum = {}
    for ent, fields in row["entity_fields"].items():
        for fld in fields:
            momentum[f"{ent}.{fld}"] = {"status": "flat", "delta_window": 0, "since": "2026-09-01"}
    momentum["boards.pinout"]["status"] = "stale"
    md = data_snapshot.render_markdown(gauge, row, None, momentum)
    assert "## Field coverage" in md
    assert "boards.pinout: 1 (33.3%) — stale" in md            # count/pct straight from the gauge
    assert "(!)" in md                                          # stale is clearly marked
    # worst-pct first: images (0%) sits above the higher-pct usb_serial line
    assert md.index("boards.images:") < md.index("boards.usb_serial:")


# --- CLI ------------------------------------------------------------------

def test_cli_main_writes_both_files(tmp_path):
    _build_fixture(tmp_path)
    rc = data_snapshot.main(["--repo-root", str(tmp_path), "--date", "2026-09-09"])
    assert rc == 0
    assert (tmp_path / "docs" / "telemetry" / "data-trend.jsonl").exists()
    assert (tmp_path / "docs" / "telemetry" / "data-2026-09-09.md").exists()
