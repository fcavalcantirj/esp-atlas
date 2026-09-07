"""Tests for scripts/derive_getting_started.py — on tmp copies of real board.md files with
a fake HEAD, so the real data/ tree is never written and no network is touched."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import derive_getting_started as dgs

REPO = Path(__file__).resolve().parent.parent
BOARDS = REPO / "data" / "boards"
TODAY = "2026-09-07"
GUIDE = "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html"


def _copy(board_rel: str, tmp_path: Path) -> Path:
    """A tmp copy restored to its pre-derivation state (the real file may already carry a
    derived getting_started from a committed run)."""
    import re
    src = BOARDS / board_rel / "board.md"
    text = src.read_text(encoding="utf-8")
    text = re.sub(r"^getting_started: .*\n", "", text, flags=re.M)
    text = re.sub(r"^- field: getting_started\n  url: [^\n]+\n  verified: '[^\n]+'\n", "", text, flags=re.M)
    dst = tmp_path / "board.md"
    dst.write_text(text, encoding="utf-8")
    return dst


def _fm(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


def test_candidates_only_vendor_guide_urls():
    fm = {"sources": [
        {"field": "*", "url": GUIDE},
        {"field": "socs", "url": "https://github.com/espressif/arduino-esp32/blob/master/boards.txt"},
        {"field": "usb", "url": "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/index.html"},
        {"field": "x", "url": "https://learn.adafruit.com/adafruit-feather-esp32-s3/getting-started-feather"},
    ]}
    assert dgs.candidates(fm) == [
        GUIDE,
        "https://learn.adafruit.com/adafruit-feather-esp32-s3/getting-started-feather",
    ]


def test_live_vendor_guide_writes_getting_started_and_source(tmp_path):
    p = _copy("espressif/esp32-devkitc-v4", tmp_path)
    line = dgs.process_file(p, TODAY, head=lambda u: u == GUIDE)
    assert line.endswith(f"getting_started={GUIDE}")
    fm = _fm(p)
    assert fm["getting_started"] == GUIDE
    assert {"field": "getting_started", "url": GUIDE, "verified": TODAY} in fm["sources"]
    # idempotent: a second run writes nothing
    before = p.read_text(encoding="utf-8")
    assert dgs.process_file(p, TODAY, head=lambda u: True).endswith("already has getting_started")
    assert p.read_text(encoding="utf-8") == before


def test_dead_guide_writes_nothing(tmp_path):
    p = _copy("espressif/esp32-devkitc-v4", tmp_path)
    before = p.read_text(encoding="utf-8")
    assert dgs.process_file(p, TODAY, head=lambda u: False).endswith("no live vendor guide URL in sources)")
    assert p.read_text(encoding="utf-8") == before


def test_board_without_guide_candidate_is_skipped(tmp_path):
    p = _copy("m5stack/m5cardputer", tmp_path)   # sources are docs.m5stack.com core pages, no guide path
    before = p.read_text(encoding="utf-8")
    assert dgs.process_file(p, TODAY, head=lambda u: True).endswith("no live vendor guide URL in sources)")
    assert p.read_text(encoding="utf-8") == before
