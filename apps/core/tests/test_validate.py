import copy

import pytest
import yaml

from esp_atlas_core.frontmatter import parse_frontmatter
from esp_atlas_core.paths import REPO_ROOT
from esp_atlas_core.validate import known_ids, validate_file, validate_frontmatter, validate_markdown

SOC_PATH = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
MODULE_PATH = REPO_ROOT / "data" / "modules" / "esp32-c6-wroom-1" / "module.md"
BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"


@pytest.fixture
def soc_fm():
    fm, _body = parse_frontmatter(SOC_PATH)
    return fm


@pytest.fixture
def board_fm():
    fm, _body = parse_frontmatter(BOARD_PATH)
    return fm


def test_validate_frontmatter_valid_soc_passes(soc_fm):
    result = validate_frontmatter(soc_fm, "soc")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_missing_sources_fails(soc_fm):
    fm = copy.deepcopy(soc_fm)
    del fm["sources"]
    result = validate_frontmatter(fm, "soc")
    assert result["ok"] is False
    assert any("sources" in e for e in result["errors"])


def test_validate_frontmatter_bad_enum_fails(soc_fm):
    fm = copy.deepcopy(soc_fm)
    fm["cpu"]["arch"] = "bogus-arch"
    result = validate_frontmatter(fm, "soc")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_board_price_tier_valid_enum_passes(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["price_tier"] = "cheap"
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_price_tier_bad_enum_fails(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["price_tier"] = "priceless"
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_board_price_tier_is_optional(board_fm):
    fm = copy.deepcopy(board_fm)
    fm.pop("price_tier", None)
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_unknown_module_ref_fails(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["module"] = "does-not-exist-anywhere"
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert any("does-not-exist-anywhere" in e for e in result["errors"])


def test_validate_frontmatter_board_unknown_soc_ref_fails(board_fm):
    fm = copy.deepcopy(board_fm)
    del fm["module"]
    fm["soc"] = "does-not-exist-either"
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert any("does-not-exist-either" in e for e in result["errors"])


def test_validate_frontmatter_module_unknown_soc_ref_fails():
    fm = {
        "id": "fake-module",
        "type": "module",
        "vendor": "acme",
        "name": "Fake Module",
        "soc": "no-such-soc",
        "sources": [{"field": "*", "url": "https://example.com", "verified": "2026-08-21"}],
    }
    result = validate_frontmatter(fm, "module")
    assert result["ok"] is False
    assert any("no-such-soc" in e for e in result["errors"])


def test_validate_frontmatter_rejects_unknown_kind(soc_fm):
    result = validate_frontmatter(soc_fm, "bogus-kind")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_rejects_non_dict():
    result = validate_frontmatter(["not", "a", "dict"], "soc")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_markdown_valid_document_passes():
    text = SOC_PATH.read_text(encoding="utf-8")
    result = validate_markdown(text)
    assert result["ok"] is True
    assert result["errors"] == []
    assert result["kind"] == "soc"


def test_validate_markdown_infers_kind_from_frontmatter_type():
    text = MODULE_PATH.read_text(encoding="utf-8")
    result = validate_markdown(text)
    assert result["kind"] == "module"
    assert result["ok"] is True


def test_validate_markdown_missing_frontmatter_fails():
    result = validate_markdown("# just a heading, no frontmatter\n")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_markdown_missing_type_field_fails():
    result = validate_markdown("---\nid: no-type-here\n---\nbody\n")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_file_valid_seeded_soc_passes():
    result = validate_file(SOC_PATH)
    assert result == {"ok": True, "errors": [], "kind": "soc"}


def test_validate_file_valid_seeded_board_passes():
    result = validate_file(BOARD_PATH)
    assert result["ok"] is True
    assert result["kind"] == "board"


def test_validate_file_id_folder_mismatch_fails(tmp_path):
    text = SOC_PATH.read_text(encoding="utf-8")
    bad_dir = tmp_path / "socs" / "wrong-folder-name"
    bad_dir.mkdir(parents=True)
    bad_path = bad_dir / "chip.md"
    bad_path.write_text(text, encoding="utf-8")

    result = validate_file(bad_path)
    assert result["ok"] is False
    assert any("wrong-folder-name" in e for e in result["errors"])


def test_validate_file_board_brand_mismatch_fails(tmp_path):
    text = BOARD_PATH.read_text(encoding="utf-8")
    bad_dir = tmp_path / "boards" / "not-espressif" / "esp32-c6-devkitc-1"
    bad_dir.mkdir(parents=True)
    bad_path = bad_dir / "board.md"
    bad_path.write_text(text, encoding="utf-8")

    result = validate_file(bad_path)
    assert result["ok"] is False
    assert any("not-espressif" in e for e in result["errors"])


def test_known_ids_scans_disk_and_includes_seeded_records():
    ids = known_ids()
    assert "esp32-c6" in ids["soc"]
    assert "esp32-c6-wroom-1" in ids["module"]


def test_validate_frontmatter_uses_explicit_ids_when_given():
    fm = {
        "id": "fake-module",
        "type": "module",
        "vendor": "acme",
        "name": "Fake Module",
        "soc": "provided-soc",
        "sources": [{"field": "*", "url": "https://example.com", "verified": "2026-08-21"}],
    }
    result = validate_frontmatter(fm, "module", ids={"soc": {"provided-soc"}, "module": set()})
    assert result == {"ok": True, "errors": []}
