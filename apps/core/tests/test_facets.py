from esp_atlas_core.facets import FACET_KEYS, facets


def _values(facet):
    return [entry["value"] for entry in facet]


def test_facets_returns_every_facet_key(built_db_path):
    result = facets(db_path=built_db_path)
    assert set(result) == set(FACET_KEYS)
    for key in FACET_KEYS:
        for entry in result[key]:
            if key == "vendor_or_brand":
                assert {"value", "count", "display_name"} <= set(entry)
            else:
                assert set(entry) == {"value", "count"}
            assert entry["count"] >= 1


def test_facets_types_are_exactly_soc_module_board(built_db_path):
    result = facets(db_path=built_db_path)
    assert set(_values(result["type"])) == {"soc", "module", "board"}


def test_facets_form_factor_includes_known_values_with_counts(built_db_path):
    result = facets(db_path=built_db_path)
    by_value = {e["value"]: e["count"] for e in result["form_factor"]}
    assert by_value["devkit"] >= 1
    assert by_value["xiao"] == 3


def test_facets_form_factor_counts_sum_to_boards_with_a_form_factor(built_db_path):
    from esp_atlas_core.search import search

    result = facets(db_path=built_db_path)
    with_form = [r for r in search("", filters={"type": "board"}, db_path=built_db_path) if r["form_factor"]]
    assert sum(e["count"] for e in result["form_factor"]) == len(with_form)


def test_facets_bands_are_split_tokens(built_db_path):
    result = facets(db_path=built_db_path)
    values = _values(result["wifi_bands"])
    assert "2.4" in values
    assert "5" in values
    assert all("," not in v for v in values)


def test_facets_protocols_are_split_tokens(built_db_path):
    result = facets(db_path=built_db_path)
    values = _values(result["ieee802154_protocols"])
    assert any(v.startswith("zigbee") for v in values)
    assert any(v.startswith("thread") for v in values)
    assert all("," not in v for v in values)


def test_facets_price_tiers_are_a_subset_of_the_known_tiers(built_db_path):
    result = facets(db_path=built_db_path)
    assert set(_values(result["price_tier"])).issubset({"cheap", "medium", "expensive"})


def test_facets_are_sorted_by_count_desc_then_value(built_db_path):
    result = facets(db_path=built_db_path)
    for key in FACET_KEYS:
        keys = [(-e["count"], e["value"]) for e in result[key]]
        assert keys == sorted(keys), key


def test_facets_never_contain_null_or_empty_values(built_db_path):
    result = facets(db_path=built_db_path)
    for key in FACET_KEYS:
        assert all(e["value"] for e in result[key]), key


def test_facets_vendor_or_brand_known_slug_gets_editorial_display_name(built_db_path):
    result = facets(db_path=built_db_path)
    by_value = {e["value"]: e for e in result["vendor_or_brand"]}
    assert by_value["espressif"]["display_name"] == "Espressif"
    assert by_value["espressif"]["url"] == "https://www.espressif.com"
    assert by_value["unexpected-maker"]["display_name"] == "Unexpected Maker"


def test_facets_vendor_or_brand_unknown_slug_falls_back_to_slug(tmp_path, monkeypatch):
    from esp_atlas_core import index_build

    data_dir = tmp_path / "data"
    _seed_minimal_dataset(data_dir, brand="no-brand-file")
    # _row_for stores each record's path relative to REPO_ROOT; a data_dir outside
    # the real repo needs REPO_ROOT patched to match, same as the tmp_path tree.
    monkeypatch.setattr(index_build, "REPO_ROOT", tmp_path)
    db_path = tmp_path / "esp-atlas.db"
    index_build.build_index(db_path=db_path, data_dir=data_dir)

    result = facets(db_path=db_path)
    by_value = {e["value"]: e for e in result["vendor_or_brand"]}
    assert by_value["no-brand-file"]["display_name"] == "no-brand-file"
    assert "url" not in by_value["no-brand-file"]


def _seed_minimal_dataset(data_dir, brand):
    """A single bare-chip board with no data/brands/<brand>/ record, for testing
    the facets() display_name fallback in isolation from the real seeded dataset."""
    soc_dir = data_dir / "socs" / "fake-soc"
    soc_dir.mkdir(parents=True)
    (soc_dir / "chip.md").write_text(
        "---\n"
        "id: fake-soc\n"
        "type: soc\n"
        "vendor: acme\n"
        "name: Fake SoC\n"
        "sources:\n"
        "- field: '*'\n"
        "  url: https://example.com\n"
        "  verified: '2026-08-22'\n"
        "---\n\nFake SoC.\n",
        encoding="utf-8",
    )
    board_dir = data_dir / "boards" / brand / "fake-board"
    board_dir.mkdir(parents=True)
    (board_dir / "board.md").write_text(
        f"---\n"
        f"id: fake-board\n"
        f"type: board\n"
        f"brand: {brand}\n"
        f"name: Fake Board\n"
        f"soc: fake-soc\n"
        f"sources:\n"
        f"- field: '*'\n"
        f"  url: https://example.com\n"
        f"  verified: '2026-08-22'\n"
        f"---\n\nFake board.\n",
        encoding="utf-8",
    )
