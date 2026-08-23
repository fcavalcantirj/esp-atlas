from esp_atlas_core.frontmatter import parse_frontmatter, DATA_PATTERNS, iter_data_files
from esp_atlas_core.paths import REPO_ROOT


def test_parse_frontmatter_splits_yaml_and_body():
    path = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
    fm, body = parse_frontmatter(path)
    assert fm["id"] == "esp32-c6"
    assert fm["type"] == "soc"
    assert fm["radios"]["ieee802154"]["present"] is True
    assert "IoT all-rounder" in body


def test_parse_frontmatter_rejects_missing_frontmatter(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("# no frontmatter here\n")
    try:
        parse_frontmatter(bad)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_iter_data_files_finds_all_four_types():
    found = list(iter_data_files())
    types = {t for t, _ in found}
    assert types == {"soc", "module", "board", "brand"}
    # every real seeded soc shows up
    soc_paths = [p for t, p in found if t == "soc"]
    assert any(p.name == "chip.md" and p.parent.name == "esp32-c6" for p in soc_paths)
    # every real seeded brand shows up
    brand_paths = [p for t, p in found if t == "brand"]
    assert any(p.name == "brand.md" and p.parent.name == "espressif" for p in brand_paths)


def test_data_patterns_match_existing_scripts_conventions():
    assert DATA_PATTERNS["soc"].endswith("chip.md")
    assert DATA_PATTERNS["module"].endswith("module.md")
    assert DATA_PATTERNS["board"].endswith("board.md")
    assert DATA_PATTERNS["brand"].endswith("brand.md")
