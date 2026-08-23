from esp_atlas_core.firmware import (
    get_firmware,
    list_firmware,
    list_recipes,
    recipes_for_board,
    recipes_for_firmware,
)


def test_list_firmware_includes_every_seeded_firmware():
    firmware = list_firmware()
    ids = {fm["id"] for fm in firmware}
    assert ids == {
        "esp32marauder",
        "m5stick-nemo",
        "m5-crystal",
        "infiltra",
        "rogueduck",
        "launcher",
    }


def test_get_firmware_known_id_returns_full_record():
    fm = get_firmware("esp32marauder")
    assert fm["name"] == "ESP32 Marauder"
    assert fm["url"] == "https://github.com/justcallmekoko/ESP32Marauder"
    assert fm["category"] == "pentest"
    assert set(fm["socs"]) == {"esp32", "esp32-s2", "esp32-s3"}


def test_get_firmware_unknown_id_returns_none():
    assert get_firmware("no-such-firmware") is None


def test_list_recipes_includes_every_seeded_recipe():
    recipes = list_recipes()
    ids = {r["id"] for r in recipes}
    assert ids == {
        "m5cardputer__esp32marauder",
        "m5stick-cplus2__esp32marauder",
        "m5cardputer__m5stick-nemo",
        "m5cardputer__launcher",
        "m5stick-cplus2__launcher",
        "m5stack-cores3__launcher",
        "m5stack-core2__launcher",
        "lilygo-t-deck__launcher",
        "lilygo-t-embed__launcher",
        "lilygo-t-display-s3__launcher",
        "lilygo-t-dongle-s3__launcher",
        "lilygo-t-watch-s3__launcher",
        "lilygo-t-display-s3-amoled__launcher",
    }


def test_recipes_for_board_filters_by_board():
    recipes = recipes_for_board("m5cardputer")
    ids = {r["id"] for r in recipes}
    assert ids == {
        "m5cardputer__esp32marauder",
        "m5cardputer__m5stick-nemo",
        "m5cardputer__launcher",
    }


def test_recipes_for_board_unknown_board_returns_empty():
    assert recipes_for_board("no-such-board") == []


def test_recipes_for_firmware_filters_by_firmware():
    recipes = recipes_for_firmware("launcher")
    ids = {r["id"] for r in recipes}
    assert ids == {
        "m5cardputer__launcher",
        "m5stick-cplus2__launcher",
        "m5stack-cores3__launcher",
        "m5stack-core2__launcher",
        "lilygo-t-deck__launcher",
        "lilygo-t-embed__launcher",
        "lilygo-t-display-s3__launcher",
        "lilygo-t-dongle-s3__launcher",
        "lilygo-t-watch-s3__launcher",
        "lilygo-t-display-s3-amoled__launcher",
    }


def test_recipes_for_firmware_unknown_firmware_returns_empty():
    assert recipes_for_firmware("no-such-firmware") == []


def test_every_recipe_status_is_known_good():
    assert all(r["status"] == "known-good" for r in list_recipes())
