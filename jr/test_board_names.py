"""jr/board_names.py — the catalogued boards a text names, from the catalog's own vocabulary.
Unit rules on sentences, then a replay over the 92 repos the topics stage rejected
`no_board_evidence` on 2026-11-17 (jr/fixtures/board_names/no_board_evidence_2026-11-17.json)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import board_names

REPO = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((REPO / "jr" / "fixtures" / "board_names" / "no_board_evidence_2026-11-17.json").read_text())


def named(text, topics=()):
    return board_names.boards_named_in(text, REPO, topics=topics)


@pytest.mark.parametrize("text, expected", [
    ("GNSS logger for the Heltec Wireless Tracker", ["heltec-wireless-tracker"]),  # brand + name
    ("heltec-wireless-tracker firmware", ["heltec-wireless-tracker"]),              # the catalog id
    ("Spotify remote for the LilyGO T-Display S3.", ["lilygo-t-display-s3"]),
    ("music on a lilygo-tdisplay-s3", ["lilygo-t-display-s3"]),                     # separators optional
    ("A remote on the T-Display S3 (ESP32-S3)", ["lilygo-t-display-s3"]),           # digit-bearing bare name
    ("An embedded Little Smalltalk for ESP32 with SSD1306 OLED and M5StickC support", ["m5stick-c"]),
    ("ESP32-S3-DevKitC-1 based sampler", ["esp32-s3-devkitc-1"]),
    ("Dashboard for the Inkplate 6", ["soldered-inkplate-6"]),
    ("M5Stack Fire port", ["m5stack-fire"]),
    ("Weather on the Adafruit MagTag", ["adafruit-magtag"]),
    ("adafruit_magtag29_esp32s2 build", ["adafruit-magtag"]),                       # an aka (toolchain id)
])
def test_a_board_is_named_by_its_id_its_brand_and_name_an_aka_or_a_digit_bearing_name(text, expected):
    assert named(text) == expected


@pytest.mark.parametrize("text", [
    "Embedded Rust on Espressif training material. esp32 esp32-c3 rust-embedded",   # 'tembed' inside 'rust-embedded'
    "Wireless tracker for dogs on ESP32",                                           # English words, no brand
    "runs on the Fire",                                                             # a product line, no brand
    "MagTag weather",                                                               # coined but digitless: needs its brand
    "T-Deck chat",                                                                  # digitless bare name: needs LilyGO
    "ESP32-S3 generic firmware, esp32s3 devkit",                                    # chip-only and generic words
    "M5Cardputer Arduino library for anything",                                     # a library reference is not a device
    "https://github.com/lilygo/t-display-s3-examples",                              # a URL is not prose
    "Intel Core2Duo benchmark port",                                                # 'core2' inside a longer word
    # #1797 review: a brandless coined name ("PaperS3", "TinyS3", "Core2") is one word in the catalog;
    # a separator inside it turns it into an English phrase that names no board
    "Weather station for the LilyGO T5 4.7 inch E-Paper S3",                        # 'paper s3' is not the PaperS3
    "CrowPanel ESP32 E-Paper S3 HMI",
    "a tiny S3 board",                                                              # not the UM TinyS3
    "Pro S3 board",                                                                 # not the UM ProS3
    "dual core 2.4 GHz",                                                            # not the M5Stack Core2
    "M5Stack AtomS3R camera demo",                                                  # the S3R is a sibling, not the AtomS3
    # #1797 second review: a name made only of chip and module words is the module, not a board;
    # a catalogued name followed by a variant word is that variant, an uncatalogued sibling
    "Camera web streamer for the ESP32-WROVER module with PSRAM",                   # not the Freenove board
    "ESP32-WROVER-E board with PSRAM",
    "esp32 wrover kit audio",
    "E-paper clock for the M5Stack Core Ink",                                       # the CoreInk, not the Core
    "Spotify remote for the LilyGO T-Display S3 Pro",                               # nor the T-Display (general)
    "LilyGO T-Display-S3-Pro firmware",
    "Heltec Wireless Tracker v2 logger",
    # #1797 third review: the word after a name is an open set, so an unknown word is a sibling until proven
    # otherwise. ("Quasar" is invented on purpose: a real sibling may be catalogued tomorrow, as the T-Beam
    # Supreme was on 2026-11-20 while this was in review; the real ones are in the test below.)
    "Mesh node for the LilyGO T-Beam Quasar",
    "lilygo t-beam quasar mesh node",                                               # lower case gives no hint either
    "LilyGO T-Display-S3-Quasar firmware",
    # ... and a chip-first catalog name is an English phrase unless it is spelled as the catalog spells it
    "Modbus gateway for any ESP32 Ethernet kit like the WT32-ETH01",
    "an ESP32 Ethernet kit.",
    "ESP32 S3 DevKitC 1 sampler",
    "",
])
def test_a_board_is_never_named_by_a_substring_an_english_word_a_chip_or_a_library_reference(text):
    assert named(text) == []


def test_a_bare_digitless_name_needs_its_brand_or_a_known_vendor_prefix():
    assert named("Chat for the LilyGO T-Deck") == ["lilygo-t-deck"]
    assert named("A tracker on the TTGO T-Beam.") == ["lilygo-t-beam"]
    assert named("A thing for the M5 StickC") == ["m5stick-c"]


def test_a_brandless_coined_name_matches_only_as_the_catalog_spells_it_but_its_brand_frees_the_separators():
    assert named("A clock on the PaperS3") == ["m5stack-papers3"]
    assert named("A synth for the TinyS3.") == ["um-tinys3"]
    assert named("A clock on the M5Stack Paper S3") == ["m5stack-papers3"]          # brand + name
    assert named("A synth for the Unexpected Maker Tiny S3") == ["um-tinys3"]
    assert named("A remote on the T-Display S3") == ["lilygo-t-display-s3"]        # the catalog's own word break


def test_the_specific_board_wins_over_the_general_one_it_contains():
    assert named("A remote on the T-Display S3") == ["lilygo-t-display-s3"]        # not also lilygo-t-display
    assert named("A scope for the StickC Plus2") == ["m5stick-cplus2"]              # not also m5stick-c / cplus
    assert named("lilygo-t-display-s3-amoled demo") == ["lilygo-t-display-s3-amoled"]


@pytest.mark.parametrize("after", ["", ".", ", with GPS", " (ESP32)", "; then", ": notes", "!", " / T-Deck", "'s screen",
                                   " and a GPS", " with LoRa", " for hikers", " board", " boards", " firmware",
                                   " support", " based tracker", " port", " demo", " build", " running MicroPython"])
def test_a_name_counts_when_what_follows_is_the_end_punctuation_or_a_plain_word(after):
    assert "lilygo-t-beam" in named("Tracker for the LilyGO T-Beam" + after)


@pytest.mark.parametrize("after", [" Quasar", " quasar", "-Quasar", "_quasar", " Q7", " v9.9", " 9.9", " ZX81", " Longer",
                                   " Meshtastic", " GPS", " tracker", " mesh", " Pro", " Plus", " AXP2101", " edition",
                                   " Supreme", "-Supreme", " S3"])
def test_any_other_word_right_after_a_name_never_names_that_board(after):
    """An unknown word names nothing; a sibling that IS catalogued names itself, never the base board."""
    got = named("Tracker for the LilyGO T-Beam" + after)
    assert "lilygo-t-beam" not in got
    if "quasar" in after.lower() or after in (" Q7", " v9.9", " 9.9", " ZX81", " Longer", " tracker", " mesh", " edition"):
        assert got == []


@pytest.mark.parametrize("text, base, sibling", [
    ("Mesh node for the LilyGO T-Beam Supreme", "lilygo-t-beam", "lilygo-t-beam-supreme"),     # ESP32-S3; the T-Beam is ESP32
    ("lilygo t-beam supreme.", "lilygo-t-beam", "lilygo-t-beam-supreme"),
    ("Sub-GHz scanner firmware for the LilyGO T-Embed CC1101", "lilygo-t-embed", "lilygo-t-embed-cc1101"),
    ("Dashboard for the LilyGO T-Display S3 Long", "lilygo-t-display-s3", "lilygo-t-display-s3-long"),
    ("LilyGO T-Display-S3-Long firmware", "lilygo-t-display-s3", "lilygo-t-display-s3-long"),
])
def test_a_real_sibling_never_names_the_base_board_and_names_itself_once_it_is_catalogued(text, base, sibling):
    import board_alias
    got = named(text)
    assert base not in got and "lilygo-t-display" not in got
    assert got == ([sibling] if sibling in board_alias.atlas_boards(REPO) else [])


def test_a_topic_names_a_board_only_when_the_whole_topic_is_the_boards_name():
    """Topics are labels the author typed one by one: a whole topic is a name with nothing after it."""
    assert named("", topics=["esp32", "m5stickc", "odroid-go"]) == ["m5stick-c"]
    assert named("", topics=["lilygo-tdisplay-s3", "music", "playlists"]) == ["lilygo-t-display-s3"]
    assert named("", topics=["t-display-s3"]) == ["lilygo-t-display-s3"]            # a digit-bearing bare name
    assert named("", topics=["m5stack-cardputer", "m5stack-stickc"]) == ["m5cardputer", "m5stick-c"]
    assert named("", topics=["esp32-ethernet-kit"]) == ["esp32-ethernet-kit"]
    # a sibling's topic carries its suffix; a digitless bare name needs its brand; a chip is no board
    assert named("", topics=["t-beam-quasar", "lilygo-t-beam-quasar", "tbeam-quasar-mesh", "t-embed-zx81"]) == []
    assert "lilygo-t-beam" not in named("", topics=["t-beam-supreme", "lilygo-t-beam-supreme", "tbeam-supreme-mesh"])
    assert named("", topics=["t-deck", "fire", "wireless-tracker", "esp32-s3", "esp32s3", "lilygo", "m5stack"]) == []
    assert named("", topics=["lilygo-t-deck"]) == ["lilygo-t-deck"]
    assert named("A clock.", topics=None) == []


def test_two_different_boards_are_both_named_and_the_caller_decides():
    assert named("Smart home remotes for the M5StickC and the M5StickC Plus") == ["m5stick-c", "m5stick-cplus"]


def test_replay_the_92_rejected_repos_of_2026_11_17():
    """What the scorer missed with 14 of 118 boards in its vocabulary: 14 of 92 repos (10 above the
    star floor) name a catalogued board in their own name, description or topics; none of the other
    78 is named a board it does not say (the fixture's `expected` is hand-reviewed). Two hits of the
    first version are gone, each with a `note` in the fixture: one was the end of a description glued to
    a topic (never a hit), one is a real miss of the fail-closed rule (the name is followed by an
    ordinary word the rule cannot tell from a sibling's suffix)."""
    hits_all, hits_floor = 0, 0
    for case in FIXTURE["cases"]:
        got = sorted(set(named(case["repo"].split("/")[1])) | set(named(case["description"], case["topics"])))
        assert got == case["expected"], (case["repo"], got, case["expected"])
        hits_all += bool(got)
        hits_floor += bool(got) and case["stars"] >= 25
    assert (hits_all, hits_floor) == (14, 10)
    assert named(" ".join(c["description"] or "" for c in FIXTURE["cases"] if c["repo"] == "esp-rs/std-training")) == []


def test_a_module_word_or_a_variant_word_only_refuses_what_it_touches():
    """#1797 second review: the brand keeps a module-named board ("Freenove ESP32-WROVER"); a word
    after the name that is not a variant word ("with", "GNSS", "remote") leaves the board named."""
    assert named("Camera kit for the Freenove ESP32-WROVER") == ["freenove-esp32-wrover"]
    assert named("freenove_esp32_wrover build") == ["freenove-esp32-wrover"]
    assert named("M5Stack Core with a LoRa module") == ["m5stack-core"]
    assert named("A basic clock for the M5Stack Core.") == ["m5stack-core"]
    assert named("Spotify remote for the LilyGO T-Display S3") == ["lilygo-t-display-s3"]
    assert named("LilyGO T-Display S3 AMOLED demo") == ["lilygo-t-display-s3-amoled"]   # a catalogued variant
    assert named("LilyGO T-Display S3 Spotify remote") == []                            # unknown word: fail closed
    assert named("Espressif ESP32 Ethernet Kit gateway.") == []                         # "gateway": fail closed
    assert named("Gateway for the Espressif ESP32 Ethernet Kit.") == ["esp32-ethernet-kit"]   # the brand frees the spelling
    assert named("Gateway for the ESP32-Ethernet-Kit") == ["esp32-ethernet-kit"]
