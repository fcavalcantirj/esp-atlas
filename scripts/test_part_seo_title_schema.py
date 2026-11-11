"""TDD tests for the optional `seo_title` override on part records (SPEC-serp-ctr.md §3,
Brief A2): schema/soc.schema.json, schema/module.schema.json and schema/board.schema.json
must accept it exactly as schema/firmware.schema.json already does.

Each case writes a minimal record into tmp_path (never data/) and runs it through the real
validator, esp_atlas_core.validate.validate_file -- the same call scripts/validate.py makes.
A control case proves the minimal record is valid without `seo_title`, so a failure in the
`seo_title` case can only be the field itself.

Run: python3 -m pytest scripts/test_part_seo_title_schema.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

_CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
if str(_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(_CORE_SRC))
from esp_atlas_core.validate import validate_file  # noqa: E402

SOURCE = [{"field": "*", "url": "https://example.com/datasheet.pdf", "verified": "2026-11-10"}]

MINIMAL_RECORDS = {
    "soc": {
        "id": "esp32-test",
        "type": "soc",
        "vendor": "espressif",
        "name": "ESP32-TEST",
        "cpu": {"arch": "risc-v", "cores": 1, "max_mhz": 160},
        "memory": {"sram_kb": 400},
        "radios": {},
        "sources": SOURCE,
    },
    "module": {
        "id": "esp32-test-mini-1",
        "type": "module",
        "vendor": "espressif",
        "name": "ESP32-TEST-MINI-1",
        "soc": "esp32-test",
        "sources": SOURCE,
    },
    "board": {
        "id": "esp32-test-devkit",
        "type": "board",
        "brand": "espressif",
        "name": "ESP32-TEST DevKit",
        "soc": "esp32-test",
        "sources": SOURCE,
    },
}

# Inheritance refs resolve against these ids, not against data/, so the test is hermetic.
IDS = {"soc": {"esp32-test"}, "module": {"esp32-test-mini-1"}, "board": {"esp32-test-devkit"}}


def _write_record(root: Path, kind: str, fm: dict) -> Path:
    folder = root / "boards" / fm["brand"] if kind == "board" else root / f"{kind}s"
    path = folder / fm["id"] / f"{kind}.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\nBody.\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("kind", sorted(MINIMAL_RECORDS))
def test_minimal_part_record_is_valid_without_seo_title(tmp_path, kind):
    path = _write_record(tmp_path, kind, MINIMAL_RECORDS[kind])
    assert validate_file(path, kind=kind, ids=IDS) == {"ok": True, "errors": [], "kind": kind}


@pytest.mark.parametrize("kind", sorted(MINIMAL_RECORDS))
def test_part_record_accepts_optional_seo_title(tmp_path, kind):
    fm = {**MINIMAL_RECORDS[kind], "seo_title": f"{MINIMAL_RECORDS[kind]['name']} pinout and specs"}
    path = _write_record(tmp_path, kind, fm)
    assert validate_file(path, kind=kind, ids=IDS) == {"ok": True, "errors": [], "kind": kind}


@pytest.mark.parametrize("kind", sorted(MINIMAL_RECORDS))
def test_part_record_rejects_non_string_seo_title(tmp_path, kind):
    fm = {**MINIMAL_RECORDS[kind], "seo_title": 42}
    path = _write_record(tmp_path, kind, fm)
    assert validate_file(path, kind=kind, ids=IDS)["ok"] is False
