from esp_atlas_core.facets import FACET_KEYS, facets


def _values(facet):
    return [entry["value"] for entry in facet]


def test_facets_returns_every_facet_key(built_db_path):
    result = facets(db_path=built_db_path)
    assert set(result) == set(FACET_KEYS)
    for key in FACET_KEYS:
        for entry in result[key]:
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
