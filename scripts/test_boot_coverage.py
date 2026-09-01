"""Tests for scripts/boot_coverage.py -- the Jr backfill worklist.

Not a gate (SPEC-first-flash.md P0 keeps download_mode/usb_serial optional
while 82 boards still lack them); just a report of which boards are missing
one or both fields, for Jr to work through in P3.

Run: python3 -m pytest scripts/test_boot_coverage.py -v
"""
from __future__ import annotations
from pathlib import Path

import boot_coverage

COMPLETE_MD = """---
id: complete-board
type: board
brand: acme
name: Complete Board
soc: esp32
download_mode:
  mode: auto
usb_serial: cp2102
sources:
- field: '*'
  url: https://example.com/complete
  verified: '2026-09-01'
---

# Complete Board
"""

MISSING_BOTH_MD = """---
id: missing-both
type: board
brand: acme
name: Missing Both
soc: esp32
sources:
- field: '*'
  url: https://example.com/missing-both
  verified: '2026-09-01'
---

# Missing Both
"""

MISSING_USB_SERIAL_ONLY_MD = """---
id: missing-usb-serial
type: board
brand: acme
name: Missing USB Serial
soc: esp32
download_mode:
  mode: auto
sources:
- field: '*'
  url: https://example.com/missing-usb-serial
  verified: '2026-09-01'
---

# Missing USB Serial
"""


def _write_board(data_root, brand, board_id, text):
    d = data_root / "boards" / brand / board_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.md").write_text(text, encoding="utf-8")


def test_board_missing_both_fields_is_reported_with_both_reasons(tmp_path):
    _write_board(tmp_path, "acme", "missing-both", MISSING_BOTH_MD)
    report = boot_coverage.run(tmp_path)
    entry = next(e for e in report["missing"] if e["id"] == "missing-both")
    assert set(entry["missing_fields"]) == {"download_mode", "usb_serial"}


def test_board_missing_only_usb_serial_is_reported_with_that_reason(tmp_path):
    _write_board(tmp_path, "acme", "missing-usb-serial", MISSING_USB_SERIAL_ONLY_MD)
    report = boot_coverage.run(tmp_path)
    entry = next(e for e in report["missing"] if e["id"] == "missing-usb-serial")
    assert entry["missing_fields"] == ["usb_serial"]


def test_board_with_both_fields_is_not_reported(tmp_path):
    _write_board(tmp_path, "acme", "complete-board", COMPLETE_MD)
    report = boot_coverage.run(tmp_path)
    ids = {e["id"] for e in report["missing"]}
    assert "complete-board" not in ids


def test_run_never_forces_nonzero_exit_this_is_a_worklist_not_a_gate(tmp_path):
    _write_board(tmp_path, "acme", "missing-both", MISSING_BOTH_MD)
    exit_code = boot_coverage.main(["--data-dir", str(tmp_path)])
    assert exit_code == 0


def test_main_prints_every_missing_board(tmp_path, capsys):
    _write_board(tmp_path, "acme", "missing-both", MISSING_BOTH_MD)
    _write_board(tmp_path, "acme", "complete-board", COMPLETE_MD)
    boot_coverage.main(["--data-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "missing-both" in out
    assert "complete-board" not in out


def test_seeded_dataset_esp32_c5_devkitc_1_is_no_longer_missing():
    """Acceptance target: after P0 seeding, C5-DevKitC-1 must not appear in
    the backfill worklist."""
    report = boot_coverage.run(None)
    ids = {e["id"] for e in report["missing"]}
    assert "esp32-c5-devkitc-1" not in ids
