"""SPEC-firmware-search.md: one forgiving search box, AND filters, relevance, facets."""
from esp_atlas_core import firmware_search as fs
from esp_atlas_core.firmware import list_firmware, list_recipes

FW = [
    {"id": "ghostesp", "name": "GhostESP", "maintainer": "Spooks4576", "category": "pentest", "capabilities": ["wifi", "ble"],
     "socs": ["esp32-s3", "esp32-c6"], "distribution": ["web-flasher"], "summary": "Wireless testing toolkit.",
     "popularity": {"stars": 900, "forks": 90}, "boards": 2},
    {"id": "meshcore", "name": "MeshCore", "maintainer": "ripplebiz", "category": "mesh", "capabilities": ["lora", "mesh"],
     "socs": ["esp32-s3"], "distribution": ["releases"], "summary": "Off-grid mesh messaging over LoRa.",
     "popularity": {"stars": 500, "forks": 40}, "boards": 2},
    {"id": "meshtastic", "name": "Meshtastic", "maintainer": "meshtastic", "category": "mesh", "capabilities": ["lora", "mesh", "gps"],
     "socs": ["esp32", "esp32-s3"], "distribution": ["web-flasher"], "summary": "Mesh network; an alternative to MeshCore.",
     "popularity": {"stars": 5000, "forks": 900}, "boards": 1},
    {"id": "stack-chan", "name": "Stack-chan", "maintainer": "meganetaaan", "category": "multi", "capabilities": [],
     "socs": ["esp32"], "distribution": [], "summary": "A super-kawaii robot.", "popularity": {"stars": 100, "forks": 5}, "boards": 1},
]
RECIPES = [
    {"firmware": "ghostesp", "board": "m5cardputer", "status": "known-good"},
    {"firmware": "ghostesp", "board": "esp32-c6-devkitc-1", "status": "declared"},
    {"firmware": "meshcore", "board": "m5cardputer-adv", "status": "unverified"},
    {"firmware": "meshcore", "board": "heltec-wifi-lora-32-v3", "status": "known-good"},
    {"firmware": "meshtastic", "board": "heltec-wifi-lora-32-v3", "status": "known-good"},
    {"firmware": "stack-chan", "board": "m5stack-core2", "status": "declared"},
]
BOARDS = {"m5cardputer": "M5Stack Cardputer", "m5cardputer-adv": "M5Stack Cardputer-Adv", "m5stack-core2": "M5Stack Core2",
          "heltec-wifi-lora-32-v3": "Heltec WiFi LoRa 32 (V3)", "esp32-c6-devkitc-1": "ESP32-C6-DevKitC-1"}


def ids(**kw):
    return [r["id"] for r in fs.search_firmware(FW, RECIPES, BOARDS, **kw)]


def test_no_query_and_no_filter_is_the_whole_catalog_in_the_default_order():
    assert ids() == ["meshtastic", "ghostesp", "meshcore", "stack-chan"]          # popularity, as before


def test_a_name_is_found_whatever_the_spacing_case_or_punctuation():
    assert ids(q="ghost esp") == ["ghostesp"]
    assert ids(q="GHOSTESP") == ["ghostesp"]
    assert ids(q="stack chan") == ["stack-chan"] and ids(q="stackchan") == ["stack-chan"]


def test_filler_words_people_type_are_ignored():
    assert ids(q="ghost esp firmware") == ["ghostesp"]
    assert ids(q="stack chan firmware for flash") == ["stack-chan"]
    assert ids(q="firmware") == ids()                                             # nothing but filler: no query


def test_a_firmware_and_a_board_in_one_box():
    assert ids(q="meshcore cardputer adv") == ["meshcore"]
    assert ids(q="cardputer") == ["ghostesp", "meshcore"]                         # every firmware with a Cardputer recipe
    assert ids(q="heltec") == ["meshtastic", "meshcore"]
    assert ids(q="meshcore core2") == []                                          # every word must be found


def test_relevance_puts_the_name_before_a_mention_in_the_summary():
    assert ids(q="meshcore") == ["meshcore", "meshtastic"]                        # Meshtastic only mentions it
    assert ids(q="mesh") == ["meshtastic", "meshcore"]                            # both names: popularity breaks the tie
    assert ids(q="meshcore", sort="popularity") == ["meshtastic", "meshcore"]     # an explicit order wins


def test_filters_narrow_and_combine():
    assert ids(board="heltec-wifi-lora-32-v3") == ["meshtastic", "meshcore"]
    assert ids(soc="esp32-c6") == ["ghostesp"]
    assert ids(category="mesh") == ["meshtastic", "meshcore"]
    assert ids(capability="gps") == ["meshtastic"]
    assert ids(category="mesh", soc="esp32") == ["meshtastic"]
    assert ids(q="mesh", board="m5cardputer-adv") == ["meshcore"]


def test_tested_means_a_known_good_recipe_and_with_a_board_one_for_that_board():
    assert ids(tested=True) == ["meshtastic", "ghostesp", "meshcore"]
    assert ids(tested=True, board="m5cardputer-adv") == []                        # MeshCore is unverified there
    assert ids(tested=True, board="heltec-wifi-lora-32-v3") == ["meshtastic", "meshcore"]


def test_an_unknown_filter_value_matches_nothing_and_every_sort_mode_still_works():
    assert ids(board="no-such-board") == [] and ids(soc="z80") == [] and ids(category="nope") == []
    assert ids(category="mesh", sort="name") == ["meshcore", "meshtastic"]
    assert ids(q="mesh", sort="not-a-mode") == ["meshtastic", "meshcore"]         # clamps like sort_by_mode


def test_facets_describe_the_whole_catalog_with_counts():
    f = fs.facets(FW, RECIPES, BOARDS)
    assert f["boards"][0] == {"id": "heltec-wifi-lora-32-v3", "name": "Heltec WiFi LoRa 32 (V3)", "count": 2}
    assert {b["id"] for b in f["boards"]} == set(BOARDS)
    assert f["socs"][0] == {"id": "esp32-s3", "count": 3}
    assert {"id": "mesh", "count": 2} in f["categories"] and {"id": "lora", "count": 2} in f["capabilities"]


# --- the real catalog (SPEC §4) ------------------------------------------------------------------------

def test_the_real_catalog_answers_the_queries_people_type():
    fw, recipes, boards = list_firmware(), list_recipes(), fs.board_names()
    first = lambda q: (fs.search_firmware(fw, recipes, boards, q=q) or [{"id": None}])[0]["id"]
    assert fs.fold(first("ghost esp")) == "ghostesp"
    adv = {r["firmware"] for r in recipes if r["board"] == "m5cardputer-adv"}
    got = [r["id"] for r in fs.search_firmware(fw, recipes, boards, q="meshcore cardputer adv")]
    assert got and set(got) <= adv
    on_cardputer = {r["firmware"] for r in recipes if r["board"] == "m5cardputer"}
    assert {r["id"] for r in fs.search_firmware(fw, recipes, boards, board="m5cardputer")} == on_cardputer
    assert len(fs.search_firmware(fw, recipes, boards)) == len(fw)
