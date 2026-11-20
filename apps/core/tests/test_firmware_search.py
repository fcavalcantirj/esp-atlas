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


def test_the_maker_of_a_board_is_one_of_the_words_when_brands_are_given():
    brands = {"m5cardputer-adv": "Acme Devices", "m5stack-core2": "Acme Devices"}
    assert ids(q="acme") == []                                                    # no board id or name says Acme
    got = [r["id"] for r in fs.search_firmware(FW, RECIPES, BOARDS, brands=brands, q="acme")]
    assert got == ["meshcore", "stack-chan"]
    assert [r["id"] for r in fs.search_firmware(FW, RECIPES, BOARDS, brands=brands, q="acme meshcore")] == ["meshcore"]


def test_a_query_word_never_matches_across_two_words_of_a_summary():
    assert ids(q="gridmesh") == []                # "Off-grid mesh messaging": two words, not one
    assert ids(q="kawaii") == ["stack-chan"]      # a whole word of a summary is still found


def test_a_short_query_word_must_be_a_whole_word_of_the_record():
    assert ids(q="s3") == ["meshtastic", "ghostesp", "meshcore"]      # the esp32-s3 tag, not "plus3" or "ms3x"
    assert ids(q="ps") == [] and ids(q="hc") == []                    # inside "gps" / "meshcore": never mid-word
    assert ids(q="c6") == ["ghostesp"]
    assert ids(q="m5") == ["ghostesp", "meshcore", "stack-chan"]      # two characters may start a word: M5Stack
    assert ids(q="m5 meshcore") == ["meshcore"]
    assert ids(q="t") == [] and ids(q="m") == []                      # one character: a whole word only


def test_a_hit_at_the_start_of_a_word_outranks_one_in_the_middle():
    fw = [dict(FW[3], id="zz-mid", name="Supercore", popularity={"stars": 9000, "forks": 1}),
          dict(FW[3], id="zz-start", name="Core Runner", popularity={"stars": 1, "forks": 1})]
    assert [r["id"] for r in fs.search_firmware(fw, [], {}, q="core")] == ["zz-start", "zz-mid"]


def test_a_query_no_record_can_be_found_by_matches_nothing():
    for q in ("!!!", "? & !", "小智", "ß", "ghost esp 小智"):
        assert fs.unmatchable(q) and ids(q=q) == [], q
    for q in ("", "   ", "firmware", "the firmware for", "the-firmware", "ghost-esp!!", "c++", "wifi & ble",
              "firmware & flasher", "?? firmware"):
        assert not fs.unmatchable(q), q
    assert ids(q="firmware & flasher") == ids()                       # filler and punctuation: no query
    assert ids(q="firmware for") == ids()                             # filler only: no query at all
    assert ids(q="mesh & lora") == ids(q="mesh lora") == ["meshtastic", "meshcore"]      # punctuation between words
    assert ids(q="meshcore - cardputer + adv") == ["meshcore"]


def _write(root, kind, ident, text):
    path = root / kind / ident / ("firmware.md" if kind == "firmware" else "recipe.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_the_catalog_is_parsed_once_per_state_of_the_files(tmp_path, monkeypatch):
    from esp_atlas_core import firmware as core_firmware, frontmatter
    monkeypatch.setattr(frontmatter, "DATA_DIR", tmp_path)
    monkeypatch.setitem(fs._CATALOG, "signature", None)
    monkeypatch.setitem(fs._CATALOG, "value", None)       # both restored afterwards: no fixture leaks out
    _write(tmp_path, "firmware", "alpha", "---\nid: alpha\ntype: firmware\nname: Alpha\n---\n")
    recipe = _write(tmp_path, "recipes", "b__alpha", "---\nid: b__alpha\ntype: recipe\nboard: b\nfirmware: alpha\n---\n")
    parses = []
    real = core_firmware.parse_frontmatter
    monkeypatch.setattr(core_firmware, "parse_frontmatter", lambda p: (parses.append(p), real(p))[1])

    firmware, recipes = fs.catalog()
    assert [(f["id"], f["boards"]) for f in firmware] == [("alpha", 1)] and [r["board"] for r in recipes] == ["b"]
    first = len(parses)
    assert first == 2                             # one firmware file, one recipe file: each parsed once
    again, _ = fs.catalog()
    assert len(parses) == first and again == firmware and again is not firmware      # no parse; a fresh list

    _write(tmp_path, "firmware", "beta", "---\nid: beta\ntype: firmware\nname: Beta\n---\n")       # added
    assert [f["id"] for f in fs.catalog()[0]] == ["alpha", "beta"]
    recipe.write_text("---\nid: b__alpha\ntype: recipe\nboard: c\nfirmware: alpha\n---\n\nmoved\n", encoding="utf-8")   # edited
    assert [r["board"] for r in fs.catalog()[1]] == ["c"]
    recipe.unlink()                                                                                    # removed
    assert fs.catalog()[1] == [] and [f["boards"] for f in fs.catalog()[0]] == [0, 0]


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
    lost = [r["name"] for r in fw if r["id"] not in {x["id"] for x in fs.search_firmware(fw, recipes, boards, q=r["name"])}]
    assert lost == []                                                 # every firmware is found by its own name
    on_m5 = {r["firmware"] for r in recipes if r["board"].startswith("m5")}
    m5 = {r["id"] for r in fs.search_firmware(fw, recipes, boards, q="m5")}
    assert len(m5) > 100 and on_m5 <= m5
    assert fs.search_firmware(fw, recipes, boards, q="m5 nemo")[0]["id"] == "m5stick-nemo"
    infrared = {r["id"] for r in fw if "ir" in (r.get("capabilities") or [])}
    found = fs.search_firmware(fw, recipes, boards, q="ir")
    assert infrared and infrared <= {r["id"] for r in found} and len(found) < len(fw) // 4
    assert {r["id"] for r in found[:len(infrared)]} & infrared        # the tagged ones are not buried
