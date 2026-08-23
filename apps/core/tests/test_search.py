import pytest

from esp_atlas_core.search import get_part, search


def test_search_free_text_finds_matching_records(built_db_path):
    results = search("zigbee", filters={}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-c6" in ids
    assert "esp32-h2" in ids
    # something with no zigbee mention should not show up
    assert "esp32-s2" not in ids


def test_search_structured_filter_ieee802154(built_db_path):
    results = search("", filters={"ieee802154": True}, db_path=built_db_path)
    assert len(results) > 0
    for r in results:
        assert r["ieee802154"] is True


def test_search_structured_filter_form_factor(built_db_path):
    results = search("", filters={"form": "xiao"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "xiao-esp32c6" in ids
    assert "xiao-esp32c3" in ids
    for r in results:
        assert r["type"] == "board"
        assert r["form_factor"] == "xiao"


def test_search_structured_filter_band(built_db_path):
    results = search("", filters={"band": 5}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-s3" not in ids  # s3 is 2.4 GHz only
    assert len(results) > 0
    for r in results:
        assert "5" in (r["wifi_bands"] or "").split(",")


def test_search_structured_filter_band_accepts_float(built_db_path):
    # CLI options are declared as type=float, so 5 arrives as 5.0 — must still match the "5" token.
    results = search("", filters={"band": 5.0}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-c5" in ids
    for r in results:
        assert "5" in (r["wifi_bands"] or "").split(",")


def test_search_structured_filter_band_float_2_4_still_matches(built_db_path):
    results = search("", filters={"band": 2.4}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-s3" in ids
    for r in results:
        assert "2.4" in (r["wifi_bands"] or "").split(",")


def test_search_structured_filter_radio_standard(built_db_path):
    results = search("", filters={"radio": "wifi-6"}, db_path=built_db_path)
    assert len(results) > 0
    for r in results:
        assert r["wifi_standard"] == "wifi-6"


def test_search_radio_wifi6_excludes_wifi4_only_parts(built_db_path):
    results = search("", filters={"radio": "wifi-6"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-devkitc-v4" not in ids  # classic ESP32 board is wifi-4 only


def test_search_radio_wifi4_is_a_minimum_and_also_matches_wifi6_parts(built_db_path):
    results = search("", filters={"radio": "wifi-4"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-devkitc-v4" in ids  # wifi-4 board
    assert "esp32-c6-devkitc-1" in ids  # wifi-6 board, backward compatible with wifi-4
    for r in results:
        assert r["wifi_standard"] in ("wifi-4", "wifi-6")


def test_search_radio_filter_excludes_parts_with_no_wifi(built_db_path):
    results = search("", filters={"radio": "wifi-4"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-h2-devkitm-1" not in ids  # ESP32-H2 has no Wi-Fi radio at all


def test_search_radio_unknown_standard_raises(built_db_path):
    with pytest.raises(ValueError):
        search("", filters={"radio": "wifi-99"}, db_path=built_db_path)


def test_search_combines_query_and_filters(built_db_path):
    results = search("thread", filters={"type": "soc"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-h2" in ids
    for r in results:
        assert r["type"] == "soc"


def test_search_returns_expected_record_shape(built_db_path):
    results = search("", filters={"type": "soc", "radio": "wifi-6"}, db_path=built_db_path)
    assert results
    r = results[0]
    for key in ("id", "type", "name", "_path", "sources"):
        assert key in r
    assert isinstance(r["sources"], list)
    assert r["sources"][0]["url"].startswith("http")


def test_search_no_results_returns_empty_list(built_db_path):
    results = search("nonexistentkeywordxyz123", filters={}, db_path=built_db_path)
    assert results == []


def test_search_unknown_filter_raises(built_db_path):
    with pytest.raises(ValueError):
        search("", filters={"bogus": "x"}, db_path=built_db_path)


def test_search_is_deterministic(built_db_path):
    r1 = search("wifi", filters={}, db_path=built_db_path)
    r2 = search("wifi", filters={}, db_path=built_db_path)
    assert [r["id"] for r in r1] == [r["id"] for r in r2]


def test_search_includes_price_tier_when_set(built_db_path):
    results = search("", filters={"form": "xiao"}, db_path=built_db_path)
    ids = {r["id"]: r for r in results}
    assert ids["xiao-esp32c3"]["price_tier"] == "cheap"


def test_search_price_tier_is_none_when_unset(built_db_path):
    results = search("", filters={"type": "soc"}, db_path=built_db_path)
    for r in results:
        assert r["price_tier"] is None


# --- soc / module filters -------------------------------------------------------


def test_search_soc_filter_returns_only_parts_on_that_soc(built_db_path):
    results = search("", filters={"soc": "esp32-c6"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert {"esp32-c6", "esp32-c6-wroom-1", "esp32-c6-devkitc-1", "xiao-esp32c6"}.issubset(ids)
    for r in results:
        assert r["soc_ref"] == "esp32-c6"


def test_search_soc_filter_combines_with_type(built_db_path):
    results = search("", filters={"soc": "esp32-c6", "type": "board"}, db_path=built_db_path)
    assert results
    for r in results:
        assert r["type"] == "board"
        assert r["soc_ref"] == "esp32-c6"


def test_search_brand_filter_returns_only_parts_of_that_brand(built_db_path):
    results = search("", filters={"brand": "adafruit"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "adafruit-feather-esp32-s3" in ids
    assert results
    for r in results:
        assert r["vendor_or_brand"] == "adafruit"


def test_search_brand_filter_combines_with_type(built_db_path):
    results = search("", filters={"brand": "espressif", "type": "soc"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-c6" in ids
    for r in results:
        assert r["type"] == "soc"
        assert r["vendor_or_brand"] == "espressif"


def test_search_brand_filter_is_exact(built_db_path):
    assert search("", filters={"brand": "Adafruit"}, db_path=built_db_path) == []
    assert search("", filters={"brand": "no-such-brand"}, db_path=built_db_path) == []


def test_search_module_filter_returns_parts_using_that_module(built_db_path):
    results = search("", filters={"module": "esp32-c6-wroom-1"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "esp32-c6-devkitc-1" in ids
    for r in results:
        assert r["module_ref"] == "esp32-c6-wroom-1"


def test_search_unknown_soc_returns_empty(built_db_path):
    assert search("", filters={"soc": "esp32-nope"}, db_path=built_db_path) == []


# --- get_part ---------------------------------------------------------------------


def test_get_part_board_returns_detail_shape(built_db_path):
    part = get_part("esp32-c6-devkitc-1", db_path=built_db_path)
    assert part is not None
    # flat record fields are still there
    assert part["id"] == "esp32-c6-devkitc-1"
    assert part["wifi_standard"] == "wifi-6"
    # own frontmatter + prose body
    assert part["frontmatter"]["usb"]["connector"] == "usb-c"
    assert part["frontmatter"]["id"] == "esp32-c6-devkitc-1"
    assert part["body"].startswith("# ESP32-C6-DevKitC-1")
    # inheritance chain resolved to full records
    assert part["chain"]["module"]["id"] == "esp32-c6-wroom-1"
    assert part["chain"]["soc"]["id"] == "esp32-c6"
    # related = siblings on the same soc, excluding self and the chain parents
    related_ids = [r["id"] for r in part["related"]]
    assert "xiao-esp32c6" in related_ids
    assert "esp32-c6-devkitc-1" not in related_ids
    assert "esp32-c6" not in related_ids
    assert "esp32-c6-wroom-1" not in related_ids


def test_get_part_bare_soc_board_has_no_module_in_chain(built_db_path):
    part = get_part("xiao-esp32c6", db_path=built_db_path)
    assert part["chain"]["module"] is None
    assert part["chain"]["soc"]["id"] == "esp32-c6"
    assert part["frontmatter"]["dimensions_mm"] == [21, 17.8]


def test_get_part_soc_has_empty_chain_and_lists_parts_built_on_it(built_db_path):
    part = get_part("esp32-c6", db_path=built_db_path)
    assert part["chain"] == {"soc": None, "module": None}
    assert part["frontmatter"]["cpu"]["arch"] == "risc-v"
    related_ids = [r["id"] for r in part["related"]]
    assert "esp32-c6-wroom-1" in related_ids
    assert "xiao-esp32c6" in related_ids
    assert "esp32-c6" not in related_ids


def test_get_part_module_lists_boards_using_it(built_db_path):
    part = get_part("esp32-c6-wroom-1", db_path=built_db_path)
    assert part["chain"]["soc"]["id"] == "esp32-c6"
    assert part["chain"]["module"] is None
    assert part["frontmatter"]["flash_mb"] == 4
    related_ids = [r["id"] for r in part["related"]]
    assert "esp32-c6-devkitc-1" in related_ids
    assert "esp32-c6" not in related_ids


def test_get_part_related_is_ordered_by_type_then_name(built_db_path):
    part = get_part("esp32-c6", db_path=built_db_path)
    keys = [(r["type"], r["name"]) for r in part["related"]]
    assert keys == sorted(keys)


def test_get_part_unknown_id_returns_none(built_db_path):
    assert get_part("does-not-exist", db_path=built_db_path) is None
