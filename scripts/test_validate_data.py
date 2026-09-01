"""Tests for scripts/validate_data.py — the whole-data semantic validator.

validate_data.py reuses jr/scorer.py's own classifier (_category_from_purpose,
falling back to _category_from_capabilities) as the single source of truth for
what category a firmware entry SHOULD have, so hand-authored data/firmware/*.md
files and jr's own deterministic authoring path can never silently drift apart.

Fixtures are coding-domain firmware (a BadUSB HID tool, a LoRa mesh node, a
generic dev-toolkit multi firmware) written to a temp atlas laid out exactly
like data/firmware/<id>/firmware.md, so validate_data's file-walking and
frontmatter parsing run against something real rather than mocked out.

Run: python3 -m pytest scripts/test_validate_data.py -v
"""
from __future__ import annotations
from pathlib import Path

import pytest

import validate_data

MISCATEGORIZED_MD = """---
id: duckstrike
type: firmware
name: DuckStrike BadUSB
url: https://github.com/example/duckstrike
category: home
maintainer: example
license: MIT
socs:
- esp32-s3
capabilities:
- badusb
sources:
- field: '*'
  url: https://github.com/example/duckstrike
---

# DuckStrike BadUSB

DuckStrike BadUSB is a HID keystroke injection tool for physical-access
penetration testers.
"""

CORRECT_MD = """---
id: meshbridge
type: firmware
name: MeshBridge Node
url: https://github.com/example/meshbridge
category: mesh
maintainer: example
license: MIT
socs:
- esp32
capabilities:
- mesh
- ble
sources:
- field: '*'
  url: https://github.com/example/meshbridge
---

# MeshBridge Node

MeshBridge Node relays MeshCore packets between ESP32 nodes over LoRa.
"""

HOLE_MD = """---
id: quietcore
type: firmware
name: QuietCore Multi-Tool
url: https://github.com/example/quietcore
category: multi
maintainer: example
license: MIT
socs:
- esp32
capabilities: []
sources:
- field: '*'
  url: https://github.com/example/quietcore
---

# QuietCore Multi-Tool

QuietCore Multi-Tool is a general-purpose ESP32 firmware toolkit for developers.
"""


def _write_firmware(data_root, firmware_id, text):
    d = data_root / "firmware" / firmware_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "firmware.md").write_text(text, encoding="utf-8")


@pytest.fixture
def fixture_atlas(tmp_path):
    _write_firmware(tmp_path, "duckstrike", MISCATEGORIZED_MD)
    _write_firmware(tmp_path, "meshbridge", CORRECT_MD)
    _write_firmware(tmp_path, "quietcore", HOLE_MD)
    return tmp_path


def test_miscategorized_entry_is_reported_and_forces_nonzero_exit(fixture_atlas):
    report = validate_data.run(fixture_atlas)
    ids = {m["id"] for m in report["miscategorizations"]}
    assert "duckstrike" in ids
    duckstrike = next(m for m in report["miscategorizations"] if m["id"] == "duckstrike")
    assert duckstrike["stored"] == "home"
    assert duckstrike["expected"] == "badusb"
    assert duckstrike["signal"] == "purpose"
    assert report["exit_code"] != 0


def test_correctly_categorized_entry_is_not_flagged(fixture_atlas):
    report = validate_data.run(fixture_atlas)
    ids = {m["id"] for m in report["miscategorizations"]}
    assert "meshbridge" not in ids


def test_empty_capabilities_is_a_hole_but_does_not_force_nonzero_exit(fixture_atlas):
    report = validate_data.run(fixture_atlas)
    ids = {m["id"] for m in report["miscategorizations"]}
    assert "quietcore" not in ids  # correctly categorized despite the hole

    hole_ids = {h["id"] for h in report["holes"]}
    assert "quietcore" in hole_ids
    quietcore_holes = [h for h in report["holes"] if h["id"] == "quietcore"]
    assert any("capabilities" in h["reason"] for h in quietcore_holes)

    # only the miscategorized entry (duckstrike) should force a non-zero exit;
    # a holes-only, correctly-categorized entry must never do so on its own.
    report_holes_only = validate_data.run(fixture_atlas.parent / "does-not-exist")
    assert report_holes_only["exit_code"] == 0


def test_missing_url_and_missing_sources_are_holes(tmp_path):
    md = """---
id: bareclock
type: firmware
name: BareClock
url: ''
category: display
maintainer: example
license: MIT
socs:
- esp32
capabilities:
- display
---

# BareClock

BareClock is a minimal ESP32 clock firmware with no cited sources yet.
"""
    _write_firmware(tmp_path, "bareclock", md)
    report = validate_data.run(tmp_path)
    reasons = " ".join(h["reason"] for h in report["holes"] if h["id"] == "bareclock")
    assert "url" in reasons
    assert "sources" in reasons
    assert report["exit_code"] == 0


def test_expected_category_prefers_purpose_signal_over_capabilities():
    category, signal = validate_data.expected_category(
        name="DuckStrike BadUSB",
        capabilities=["wifi", "ble"],  # would fall back to "multi" alone
        body_text="A HID keystroke injection tool.",
    )
    assert category == "badusb"
    assert signal == "purpose"


def test_expected_category_falls_back_to_capabilities_when_no_purpose_signal():
    category, signal = validate_data.expected_category(
        name="QuietCore Multi-Tool",
        capabilities=["badusb"],
        body_text="A general-purpose ESP32 firmware toolkit for developers.",
    )
    assert category == "badusb"
    assert signal == "capabilities"


def test_main_exits_nonzero_only_on_miscategorization(fixture_atlas, capsys):
    exit_code = validate_data.main(["--data-dir", str(fixture_atlas)])
    assert exit_code != 0
    out = capsys.readouterr().out
    assert "MISCATEGORIZ" in out.upper()
    assert "duckstrike" in out


def test_main_exits_zero_when_only_holes_present(tmp_path, capsys):
    _write_firmware(tmp_path, "meshbridge", CORRECT_MD)
    _write_firmware(tmp_path, "quietcore", HOLE_MD)
    exit_code = validate_data.main(["--data-dir", str(tmp_path)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "quietcore" in out
