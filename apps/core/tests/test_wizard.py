import pytest

from esp_atlas_core.wizard import wizard


def test_wizard_protocol_need_ranks_matching_parts_first(built_db_path):
    results = wizard({"protocol": "zigbee"}, db_path=built_db_path)
    assert results
    ids = {r["id"] for r in results}
    assert "esp32-c6" in ids
    assert "esp32-h2" in ids
    assert "esp32-s2" not in ids  # no 802.15.4 at all
    for r in results:
        assert r["score"] > 0
        assert any("zigbee" in reason.lower() for reason in r["reasons"])


def test_wizard_usb_native_need(built_db_path):
    results = wizard({"usb_native": True}, db_path=built_db_path)
    assert results
    for r in results:
        assert r["usb_native"] is True
        assert any("usb" in reason.lower() for reason in r["reasons"])


def test_wizard_ieee802154_need_returns_only_802_15_4_capable_parts(built_db_path):
    results = wizard({"ieee802154": True}, db_path=built_db_path)
    assert results
    ids = {r["id"] for r in results}
    assert "esp32-c6" in ids
    assert "esp32-h2" in ids
    assert "esp32-s2" not in ids  # no 802.15.4 at all
    for r in results:
        assert r["ieee802154"] is True
        assert r["score"] > 0
        assert any("802.15.4" in reason for reason in r["reasons"])


def test_wizard_ieee802154_unset_or_false_does_not_filter(built_db_path):
    no_need = wizard({}, db_path=built_db_path)
    unset_ids = {r["id"] for r in no_need}
    false_need = wizard({"ieee802154": False}, db_path=built_db_path)
    false_ids = {r["id"] for r in false_need}
    assert unset_ids == false_ids
    assert "esp32-s2" in unset_ids  # a non-802.15.4 part is still present


def test_wizard_combines_multiple_hard_needs(built_db_path):
    results = wizard({"protocol": "zigbee", "usb_native": True}, db_path=built_db_path)
    assert results
    for r in results:
        assert r["usb_native"] is True


def test_wizard_budget_is_not_scored(built_db_path):
    results = wizard({"budget": "cheap"}, db_path=built_db_path)
    assert results
    for r in results:
        assert r["score"] == 0
        assert any("budget" in reason.lower() for reason in r["reasons"])


def test_wizard_budget_cheap_excludes_medium_tier_but_keeps_unknown_tier(built_db_path):
    results = wizard({"budget": "cheap"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "xiao-esp32c3" in ids  # price_tier: cheap
    assert "esp32-s3-devkitc-1" not in ids  # price_tier: medium, over the ceiling
    assert "esp32-c6" in ids  # soc, no price_tier at all -> always included


def test_wizard_budget_medium_includes_cheap_and_medium_tiers(built_db_path):
    results = wizard({"budget": "medium"}, db_path=built_db_path)
    ids = {r["id"] for r in results}
    assert "xiao-esp32c3" in ids  # cheap
    assert "esp32-s3-devkitc-1" in ids  # medium
    assert "esp32-c6" in ids  # unknown tier, still included


def test_wizard_budget_expensive_matches_no_budget_at_all(built_db_path):
    with_budget = wizard({"budget": "expensive"}, db_path=built_db_path)
    no_budget = wizard({}, db_path=built_db_path)
    assert {r["id"] for r in with_budget} == {r["id"] for r in no_budget}


def test_wizard_empty_budget_string_means_no_price_filtering(built_db_path):
    with_empty_budget = wizard({"budget": ""}, db_path=built_db_path)
    no_budget = wizard({}, db_path=built_db_path)
    assert {r["id"] for r in with_empty_budget} == {r["id"] for r in no_budget}


def test_wizard_rejects_invalid_budget_value(built_db_path):
    with pytest.raises(ValueError):
        wizard({"budget": "low"}, db_path=built_db_path)


def test_wizard_budget_combines_with_hard_needs(built_db_path):
    results = wizard({"form": "xiao", "budget": "cheap"}, db_path=built_db_path)
    assert results
    ids = {r["id"] for r in results}
    assert "xiao-esp32c3" in ids
    for r in results:
        assert r["form_factor"] == "xiao"


def test_wizard_boards_rank_above_socs_at_equal_score(built_db_path):
    results = wizard({"protocol": "thread"}, db_path=built_db_path)
    types_in_order = [r["type"] for r in results if r["score"] == results[0]["score"]]
    # within a score tier, boards (directly buyable) come first
    if "board" in types_in_order and "soc" in types_in_order:
        assert types_in_order.index("board") < types_in_order.index("soc")


def test_wizard_is_deterministic(built_db_path):
    r1 = wizard({"protocol": "matter"}, db_path=built_db_path)
    r2 = wizard({"protocol": "matter"}, db_path=built_db_path)
    assert [r["id"] for r in r1] == [r["id"] for r in r2]


def test_wizard_rejects_unknown_need(built_db_path):
    with pytest.raises(ValueError):
        wizard({"bogus": "x"}, db_path=built_db_path)


def test_wizard_no_needs_returns_everything_unscored(built_db_path):
    results = wizard({}, db_path=built_db_path)
    assert len(results) > 20  # every soc + module + board
    assert all(r["score"] == 0 for r in results)
