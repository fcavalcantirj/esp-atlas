from esp_atlas_core.firmware import (
    get_firmware,
    list_firmware,
    list_recipes,
    recipes_for_board,
    recipes_for_firmware,
)
from esp_atlas_core.paths import DATA_DIR

# The four trust tiers a recipe may carry (SPEC-wizard.md). `known-good` means
# the maintainer/an official list names the board, or esp-atlas verified it on
# real hardware; `reported` is cited but community-sourced; `unverified` is a
# plausible build target with no verification; `broken` is a known regression.
TRUST_TIERS = {"known-good", "reported", "unverified", "broken"}


def _folder_ids(kind):
    """Record ids as the data/ tree spells them -- the accessors must find exactly these."""
    return {d.name for d in (DATA_DIR / kind).iterdir() if d.is_dir()}


def test_list_firmware_includes_every_seeded_firmware():
    assert {fm["id"] for fm in list_firmware()} == _folder_ids("firmware")


def test_get_firmware_known_id_returns_full_record():
    fm = get_firmware("esp32marauder")
    assert fm["name"] == "ESP32 Marauder"
    assert fm["url"] == "https://github.com/justcallmekoko/ESP32Marauder"
    assert fm["category"] == "pentest"
    assert set(fm["socs"]) == {"esp32", "esp32-s2", "esp32-s3"}


def test_get_firmware_unknown_id_returns_none():
    assert get_firmware("no-such-firmware") is None


def test_list_recipes_includes_every_seeded_recipe():
    assert {r["id"] for r in list_recipes()} == _folder_ids("recipes")


def test_recipes_for_board_filters_by_board():
    recipes = recipes_for_board("m5cardputer")
    assert recipes, "m5cardputer should have at least one recipe"
    assert {r["id"] for r in recipes} == {
        r["id"] for r in list_recipes() if r["board"] == "m5cardputer"
    }
    assert all(r["board"] == "m5cardputer" for r in recipes)


def test_recipes_for_board_unknown_board_returns_empty():
    assert recipes_for_board("no-such-board") == []


def test_recipes_for_firmware_filters_by_firmware():
    recipes = recipes_for_firmware("launcher")
    assert recipes, "launcher should have at least one recipe"
    assert {r["id"] for r in recipes} == {
        r["id"] for r in list_recipes() if r["firmware"] == "launcher"
    }
    assert all(r["firmware"] == "launcher" for r in recipes)


def test_recipes_for_firmware_unknown_firmware_returns_empty():
    assert recipes_for_firmware("no-such-firmware") == []


def test_recipes_for_firmware_infiltra_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("infiltra")}
    assert ids == {"m5stick-cplus2__infiltra", "m5cardputer__infiltra"}


def test_recipes_for_firmware_m5_crystal_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("m5-crystal")}
    assert ids == {"m5stick-cplus2__m5-crystal", "m5stick-s3__m5-crystal"}


def test_recipes_for_firmware_rogueduck_is_no_longer_orphaned():
    ids = {r["id"] for r in recipes_for_firmware("rogueduck")}
    assert ids == {"m5stick-s3__rogueduck"}


def test_every_recipe_carries_a_valid_trust_tier():
    """Every recipe declares one of the four tiers, and says who vouched for it.

    This replaced an assertion that *every* recipe was `known-good`, which held
    only while the dataset was a hand-cited seed. `reported` (cited, but from a
    community catalogue) and `unverified` (an official build target with nothing
    shipped to verify) are legitimate tiers -- the honesty layer is that the tier
    is stated, not that it is always the highest one.
    """
    bad = [(r["id"], r.get("status")) for r in list_recipes() if r.get("status") not in TRUST_TIERS]
    assert not bad, f"recipe(s) with an unknown trust tier: {bad}"


def test_every_recipe_cites_at_least_one_source():
    uncited = [r["id"] for r in list_recipes() if not r.get("sources")]
    assert not uncited, f"uncited recipe(s): {uncited}"
