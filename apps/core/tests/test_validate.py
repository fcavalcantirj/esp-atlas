import copy

import pytest
import yaml

from esp_atlas_core.frontmatter import parse_frontmatter
from esp_atlas_core.paths import REPO_ROOT
from esp_atlas_core.validate import (
    check_orphan_firmware,
    known_ids,
    validate_file,
    validate_frontmatter,
    validate_markdown,
)

SOC_PATH = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
MODULE_PATH = REPO_ROOT / "data" / "modules" / "esp32-c6-wroom-1" / "module.md"
BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"
BRAND_PATH = REPO_ROOT / "data" / "brands" / "espressif" / "brand.md"
FIRMWARE_PATH = REPO_ROOT / "data" / "firmware" / "esp32marauder" / "firmware.md"
RECIPE_PATH = REPO_ROOT / "data" / "recipes" / "m5cardputer__esp32marauder" / "recipe.md"


@pytest.fixture
def soc_fm():
    fm, _body = parse_frontmatter(SOC_PATH)
    return fm


@pytest.fixture
def board_fm():
    fm, _body = parse_frontmatter(BOARD_PATH)
    return fm


@pytest.fixture
def brand_fm():
    fm, _body = parse_frontmatter(BRAND_PATH)
    return fm


@pytest.fixture
def firmware_fm():
    fm, _body = parse_frontmatter(FIRMWARE_PATH)
    return fm


@pytest.fixture
def recipe_fm():
    fm, _body = parse_frontmatter(RECIPE_PATH)
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


def test_validate_frontmatter_board_io_valid_passes(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["io"] = {"gpio_exposed": 22, "gpio_free": 16}
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_rejects_drive_owner_violation(board_fm):
    """`drive` is a soc-only field (SPEC-io-power.md §2) -- a board record
    physically cannot cite Espressif for its own per-pad current."""
    fm = copy.deepcopy(board_fm)
    fm["drive"] = {"gpio_source_ma_max": 40}
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_board_rejects_reserved_pins_owner_violation(board_fm):
    """`reserved_pins` is a soc-only field -- same owner rule as `drive`."""
    fm = copy.deepcopy(board_fm)
    fm["reserved_pins"] = {"strapping": [0, 2]}
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_soc_io_valid_passes(soc_fm):
    fm = copy.deepcopy(soc_fm)
    fm["drive"] = {"gpio_source_ma_max": 40, "gpio_sink_ma_max": 40}
    fm["reserved_pins"] = {"strapping": [8, 9, 15]}
    result = validate_frontmatter(fm, "soc")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_soc_rejects_io_owner_violation(soc_fm):
    """`io` (exposed/free GPIO count, power_out) is a board-only field -- the
    SoC has ~40 pads total, but only the *board* decides how many are broken
    out and free (SPEC-io-power.md §2). Espressif cannot know this."""
    fm = copy.deepcopy(soc_fm)
    fm["io"] = {"gpio_exposed": 6}
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


def test_validate_frontmatter_board_flash_mb_psram_mb_valid_passes(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["flash_mb"] = 8
    fm["psram_mb"] = 2
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_psram_mb_zero_valid_passes(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["psram_mb"] = 0
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_flash_mb_psram_mb_are_optional(board_fm):
    fm = copy.deepcopy(board_fm)
    fm.pop("flash_mb", None)
    fm.pop("psram_mb", None)
    result = validate_frontmatter(fm, "board")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_board_flash_mb_rejects_non_numeric(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["flash_mb"] = "8 MB"
    result = validate_frontmatter(fm, "board")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_file_seeded_board_with_flash_and_psram_round_trips():
    path = REPO_ROOT / "data" / "boards" / "m5stack" / "m5cardputer" / "board.md"
    result = validate_file(path)
    assert result == {"ok": True, "errors": [], "kind": "board"}

    fm, _body = parse_frontmatter(path)
    assert fm["flash_mb"] == 8
    assert fm["psram_mb"] == 0


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


def test_validate_frontmatter_valid_brand_passes(brand_fm):
    result = validate_frontmatter(brand_fm, "brand")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_brand_missing_required_field_fails(brand_fm):
    fm = copy.deepcopy(brand_fm)
    del fm["url"]
    result = validate_frontmatter(fm, "brand")
    assert result["ok"] is False
    assert any("url" in e for e in result["errors"])


def test_validate_frontmatter_brand_missing_sources_fails(brand_fm):
    fm = copy.deepcopy(brand_fm)
    del fm["sources"]
    result = validate_frontmatter(fm, "brand")
    assert result["ok"] is False
    assert any("sources" in e for e in result["errors"])


def test_validate_file_valid_seeded_brand_passes():
    result = validate_file(BRAND_PATH)
    assert result == {"ok": True, "errors": [], "kind": "brand"}


def test_validate_file_brand_id_folder_mismatch_fails(tmp_path):
    text = BRAND_PATH.read_text(encoding="utf-8")
    bad_dir = tmp_path / "brands" / "wrong-folder-name"
    bad_dir.mkdir(parents=True)
    bad_path = bad_dir / "brand.md"
    bad_path.write_text(text, encoding="utf-8")

    result = validate_file(bad_path)
    assert result["ok"] is False
    assert any("wrong-folder-name" in e for e in result["errors"])


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


def test_validate_frontmatter_valid_firmware_passes(firmware_fm):
    result = validate_frontmatter(firmware_fm, "firmware")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_firmware_missing_required_field_fails(firmware_fm):
    fm = copy.deepcopy(firmware_fm)
    del fm["category"]
    result = validate_frontmatter(fm, "firmware")
    assert result["ok"] is False
    assert any("category" in e for e in result["errors"])


def test_validate_frontmatter_firmware_bad_category_enum_fails(firmware_fm):
    fm = copy.deepcopy(firmware_fm)
    fm["category"] = "bogus-category"
    result = validate_frontmatter(fm, "firmware")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_firmware_empty_socs_fails(firmware_fm):
    fm = copy.deepcopy(firmware_fm)
    fm["socs"] = []
    result = validate_frontmatter(fm, "firmware")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_firmware_missing_sources_fails(firmware_fm):
    fm = copy.deepcopy(firmware_fm)
    del fm["sources"]
    result = validate_frontmatter(fm, "firmware")
    assert result["ok"] is False
    assert any("sources" in e for e in result["errors"])


def test_validate_file_valid_seeded_firmware_passes():
    result = validate_file(FIRMWARE_PATH)
    assert result == {"ok": True, "errors": [], "kind": "firmware"}


def test_validate_file_firmware_id_folder_mismatch_fails(tmp_path):
    text = FIRMWARE_PATH.read_text(encoding="utf-8")
    bad_dir = tmp_path / "firmware" / "wrong-folder-name"
    bad_dir.mkdir(parents=True)
    bad_path = bad_dir / "firmware.md"
    bad_path.write_text(text, encoding="utf-8")

    result = validate_file(bad_path)
    assert result["ok"] is False
    assert any("wrong-folder-name" in e for e in result["errors"])


def test_validate_frontmatter_valid_recipe_passes(recipe_fm):
    result = validate_frontmatter(recipe_fm, "recipe")
    assert result == {"ok": True, "errors": []}


def test_validate_frontmatter_recipe_missing_required_field_fails(recipe_fm):
    fm = copy.deepcopy(recipe_fm)
    del fm["status"]
    result = validate_frontmatter(fm, "recipe")
    assert result["ok"] is False
    assert any("status" in e for e in result["errors"])


def test_validate_frontmatter_recipe_bad_status_enum_fails(recipe_fm):
    fm = copy.deepcopy(recipe_fm)
    fm["status"] = "bogus-status"
    result = validate_frontmatter(fm, "recipe")
    assert result["ok"] is False
    assert result["errors"]


def test_validate_frontmatter_recipe_unknown_board_fails(recipe_fm):
    fm = copy.deepcopy(recipe_fm)
    fm["board"] = "no-such-board-anywhere"
    result = validate_frontmatter(fm, "recipe")
    assert result["ok"] is False
    assert any("no-such-board-anywhere" in e for e in result["errors"])


def test_validate_frontmatter_recipe_unknown_firmware_fails(recipe_fm):
    fm = copy.deepcopy(recipe_fm)
    fm["firmware"] = "no-such-firmware-anywhere"
    result = validate_frontmatter(fm, "recipe")
    assert result["ok"] is False
    assert any("no-such-firmware-anywhere" in e for e in result["errors"])


def test_validate_frontmatter_recipe_chip_family_mismatch_fails(recipe_fm):
    fm = copy.deepcopy(recipe_fm)
    # m5cardputer's soc is esp32-s3, not plain esp32
    fm["chip_family"] = "esp32"
    result = validate_frontmatter(fm, "recipe")
    assert result["ok"] is False
    assert any("chip_family" in e for e in result["errors"])


def test_validate_file_valid_seeded_recipe_passes():
    result = validate_file(RECIPE_PATH)
    assert result == {"ok": True, "errors": [], "kind": "recipe"}


def test_validate_file_recipe_id_folder_mismatch_fails(tmp_path):
    text = RECIPE_PATH.read_text(encoding="utf-8")
    bad_dir = tmp_path / "recipes" / "wrong-folder-name"
    bad_dir.mkdir(parents=True)
    bad_path = bad_dir / "recipe.md"
    bad_path.write_text(text, encoding="utf-8")

    result = validate_file(bad_path)
    assert result["ok"] is False
    assert any("wrong-folder-name" in e for e in result["errors"])


def test_known_ids_includes_board_and_firmware_and_board_soc():
    ids = known_ids()
    assert "m5cardputer" in ids["board"]
    assert "esp32marauder" in ids["firmware"]
    assert ids["board_soc"]["m5cardputer"] == "esp32-s3"


def test_known_ids_includes_recipe_firmware_refs():
    ids = known_ids()
    assert "esp32marauder" in ids["recipe_firmware_refs"]
    assert "infiltra" in ids["recipe_firmware_refs"]


def test_check_orphan_firmware_flags_unreferenced_firmware():
    ids = {"firmware": {"a", "b"}, "recipe_firmware_refs": {"a"}}
    errors = check_orphan_firmware(ids)
    assert errors == ["orphan firmware: no recipe references 'b'"]


def test_check_orphan_firmware_all_referenced_passes():
    ids = {"firmware": {"a", "b"}, "recipe_firmware_refs": {"a", "b"}}
    assert check_orphan_firmware(ids) == []


def test_check_orphan_firmware_reports_every_orphan_sorted():
    ids = {"firmware": {"z", "a"}, "recipe_firmware_refs": set()}
    errors = check_orphan_firmware(ids)
    assert errors == [
        "orphan firmware: no recipe references 'a'",
        "orphan firmware: no recipe references 'z'",
    ]


def test_check_orphan_firmware_seeded_dataset_passes():
    ids = known_ids()
    assert check_orphan_firmware(ids) == []
