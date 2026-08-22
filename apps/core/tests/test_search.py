import pytest

from esp_atlas_core.search import search


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
