"""Tests for scripts/derive_usb_serial.py — on tmp copies of real board.md files, so the
real data/ tree is never written."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import derive_usb_serial as dus

REPO = Path(__file__).resolve().parent.parent
BOARDS = REPO / "data" / "boards"
TODAY = "2026-09-07"


def _copy(board_rel: str, tmp_path: Path) -> Path:
    """A tmp copy restored to its pre-derivation state (the real file may already carry
    derived usb_serial from a committed run — strip it so the tests prove derivation)."""
    import re
    src = BOARDS / board_rel / "board.md"
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"^usb_serial: .*\n", "", text, flags=re.M)
    text = re.sub(r"^- field: usb_serial\n  url: [^\n]+\n  verified: '[^\n]+'\n", "", text, flags=re.M)
    text = re.sub(r"^- 'usb_serial derived from usb\.bridge[^\n]*'\n", "", text, flags=re.M)
    dst = tmp_path / "board.md"
    dst.write_text(text, encoding="utf-8")
    return dst


def _fm(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


def test_direct_values_come_from_the_schema_enum():
    schema = json.loads((REPO / "schema" / "board.schema.json").read_text())
    enum = set(schema["properties"]["usb_serial"]["enum"])
    assert dus.DIRECT <= enum, f"{dus.DIRECT - enum} not in the usb_serial enum"


def test_ch340_bridge_writes_usb_serial_source_and_note(tmp_path):
    p = _copy("dfrobot/firebeetle-esp32", tmp_path)
    line = dus.process_file(p, TODAY)
    assert "usb_serial=ch340" in line
    fm = _fm(p)
    assert fm["usb_serial"] == "ch340" and fm["usb"]["bridge"] == "ch340"
    assert {"field": "usb_serial", "url": fm["sources"][0]["url"], "verified": TODAY} in fm["sources"]
    assert "usb_serial derived from usb.bridge (ch340)" in fm["notes"]
    # idempotent: a second run writes nothing
    before = p.read_text(encoding="utf-8")
    assert dus.process_file(p, TODAY).endswith("already has usb_serial")
    assert p.read_text(encoding="utf-8") == before


def test_native_s3_bridge_resolves_serial_jtag_through_the_module(tmp_path):
    p = _copy("m5stack/m5cardputer", tmp_path)   # bridge native, soc esp32-s3 via module
    assert dus.process_file(p, TODAY).endswith("(from bridge native)")
    fm = _fm(p)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert fm["notes"][-1].startswith("usb_serial derived from usb.bridge (native) + soc usb.type")


def test_native_s2_bridge_is_left_alone(tmp_path):
    p = _copy("adafruit/adafruit-feather-esp32-s2", tmp_path)   # otg-full-speed, no serial-jtag
    before = p.read_text(encoding="utf-8")
    assert "not serial-jtag" in dus.process_file(p, TODAY)
    assert p.read_text(encoding="utf-8") == before


def test_non_enum_bridge_is_left_for_a_human(tmp_path):
    p = _copy("espressif/esp-wrover-kit", tmp_path)   # ft2232hl
    before = p.read_text(encoding="utf-8")
    assert "not a usb_serial enum value" in dus.process_file(p, TODAY)
    assert p.read_text(encoding="utf-8") == before


def test_uncited_bridge_is_skipped(tmp_path):
    p = _copy("dfrobot/firebeetle-esp32", tmp_path)
    text = p.read_text(encoding="utf-8")
    text = text.replace("- field: '*'", "- field: 'other'")   # the only bridge citation is gone
    p.write_text(text, encoding="utf-8")
    fm = _fm(p)
    assert not any(s.get("field") in ("usb.bridge", "usb", "*") for s in fm["sources"])
    before = text
    assert dus.process_file(p, TODAY).endswith("usb.bridge uncited)")
    assert p.read_text(encoding="utf-8") == before


def test_wanted_serial_matrix():
    assert dus.wanted_serial("m5cardputer", "cp2102") == ("cp2102", "bridge names cp2102")
    assert dus.wanted_serial("x", "ft231x")[0] is None
    assert dus.wanted_serial("adafruit-feather-esp32-s2", "native")[0] is None
