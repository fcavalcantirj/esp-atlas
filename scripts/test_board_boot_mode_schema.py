"""TDD tests for the P0 boot/download-mode board schema fields
(SPEC-first-flash.md): `download_mode` and `usb_serial` on schema/board.schema.json.

Deliberately lives in scripts/, not apps/core/tests/, per this task's scope
(schema/data/scripts only). Reuses esp_atlas_core.validate read-only, the same
way scripts/validate.py (the CI gate) and scripts/validate_data.py already do
-- no apps/ files are modified by this task.

Run: python3 -m pytest scripts/test_board_boot_mode_schema.py -v
"""
from __future__ import annotations
import copy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.frontmatter import parse_frontmatter  # noqa: E402
from esp_atlas_core.validate import validate_file, validate_frontmatter  # noqa: E402

BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"
C5_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c5-devkitc-1" / "board.md"


@pytest.fixture
def board_fm():
    fm, _body = parse_frontmatter(BOARD_PATH)
    return fm


def test_download_mode_manual_without_steps_is_rejected(board_fm):
    """`steps` is required when mode is 'manual' -- a manual sequence with no
    steps text is a data hole, not a valid record."""
    fm = copy.deepcopy(board_fm)
    fm["download_mode"] = {"mode": "manual"}
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_download_mode_auto_without_steps_is_valid(board_fm):
    """`auto` boards toggle EN/IO0 via DTR/RTS -- no manual steps to cite."""
    fm = copy.deepcopy(board_fm)
    fm["download_mode"] = {"mode": "auto"}
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_download_mode_manual_with_steps_is_valid(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["download_mode"] = {
        "mode": "manual",
        "steps": "Hold down Boot, then press Reset, then release Boot.",
    }
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_usb_serial_unknown_value_is_rejected(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["usb_serial"] = "some-made-up-bridge"
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_usb_serial_known_value_is_valid(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["usb_serial"] = "native-usb-serial-jtag"
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_download_mode_and_usb_serial_stay_optional(board_fm):
    fm = copy.deepcopy(board_fm)
    fm.pop("download_mode", None)
    fm.pop("usb_serial", None)
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_esp32_c5_devkitc_1_has_cited_download_mode_and_usb_serial():
    """P0 acceptance target: Felipe's own board, cited to Espressif's
    ESP32-C5-DevKitC-1 user guide, verified 2026-09-01."""
    result = validate_file(C5_PATH)
    assert result == {"ok": True, "errors": [], "kind": "board"}

    fm, _body = parse_frontmatter(C5_PATH)
    assert fm["download_mode"] == {
        "mode": "manual",
        "steps": "Hold down Boot, then press Reset, then release Boot to enter Firmware Download mode",
        "note": (
            "Two USB-C ports: the USB-to-UART port for serial flashing, or the "
            "native ESP32-C5 USB port (USB-Serial-JTAG)."
        ),
    }
    assert fm["usb_serial"] == "native-usb-serial-jtag"

    boot_mode_sources = [
        s for s in fm["sources"]
        if s["field"] in ("*", "download_mode", "usb_serial")
    ]
    assert any(
        s["url"] == "https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c5/esp32-c5-devkitc-1/user_guide.html"
        for s in boot_mode_sources
    )
