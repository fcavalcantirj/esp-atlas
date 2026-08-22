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


def test_wizard_combines_multiple_hard_needs(built_db_path):
    results = wizard({"protocol": "zigbee", "usb_native": True}, db_path=built_db_path)
    assert results
    for r in results:
        assert r["usb_native"] is True


def test_wizard_budget_need_is_accepted_but_not_scored(built_db_path):
    only_budget = wizard({"budget": "low"}, db_path=built_db_path)
    zigbee_only = wizard({}, db_path=built_db_path)
    # budget alone doesn't narrow the result set (no price data to filter on)
    assert len(only_budget) == len(zigbee_only)
    for r in only_budget:
        assert r["score"] == 0
        assert any("budget" in reason.lower() and "not modeled" in reason.lower() for reason in r["reasons"])


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
