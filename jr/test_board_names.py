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


def named(text):
    return board_names.boards_named_in(text, REPO)


@pytest.mark.parametrize("text, expected", [
    ("Heltec Wireless Tracker GNSS logger", ["heltec-wireless-tracker"]),          # brand + name
    ("heltec-wireless-tracker firmware", ["heltec-wireless-tracker"]),              # the catalog id
    ("LilyGO T-Display S3 Spotify remote", ["lilygo-t-display-s3"]),
    ("lilygo-tdisplay-s3 music", ["lilygo-t-display-s3"]),                          # separators optional
    ("T-Display S3 remote", ["lilygo-t-display-s3"]),                               # digit-bearing bare name
    ("An embedded Little Smalltalk for ESP32 with SSD1306 OLED and M5StickC support", ["m5stick-c"]),
    ("ESP32-S3-DevKitC-1 based sampler", ["esp32-s3-devkitc-1"]),
    ("Inkplate 6 dashboard", ["soldered-inkplate-6"]),
    ("M5Stack Fire port", ["m5stack-fire"]),
    ("Adafruit MagTag weather", ["adafruit-magtag"]),
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
    "",
])
def test_a_board_is_never_named_by_a_substring_an_english_word_a_chip_or_a_library_reference(text):
    assert named(text) == []


def test_a_bare_digitless_name_needs_its_brand_or_a_known_vendor_prefix():
    assert named("LilyGO T-Deck chat") == ["lilygo-t-deck"]
    assert named("TTGO T-Beam tracker") == ["lilygo-t-beam"]
    assert named("M5 StickC thing") == ["m5stick-c"]


def test_a_brandless_coined_name_matches_only_as_the_catalog_spells_it_but_its_brand_frees_the_separators():
    assert named("PaperS3 clock") == ["m5stack-papers3"]
    assert named("TinyS3 synth") == ["um-tinys3"]
    assert named("M5Stack Paper S3 clock") == ["m5stack-papers3"]                   # brand + name
    assert named("Unexpected Maker Tiny S3 synth") == ["um-tinys3"]
    assert named("T-Display S3 remote") == ["lilygo-t-display-s3"]                 # the catalog's own word break


def test_the_specific_board_wins_over_the_general_one_it_contains():
    assert named("T-Display S3 remote") == ["lilygo-t-display-s3"]                 # not also lilygo-t-display
    assert named("StickC Plus2 scope") == ["m5stick-cplus2"]                        # not also m5stick-c / cplus
    assert named("lilygo-t-display-s3-amoled demo") == ["lilygo-t-display-s3-amoled"]


def test_two_different_boards_are_both_named_and_the_caller_decides():
    assert named("Smart home remotes for the M5StickC and the M5StickC Plus") == ["m5stick-c", "m5stick-cplus"]


def test_replay_the_92_rejected_repos_of_2026_11_17():
    """What the scorer missed with 14 of 118 boards in its vocabulary: 16 of 92 repos (10 above the
    star floor) name a catalogued board in their own name, description or topics; none of the other
    76 is named a board it does not say (the fixture's `expected` is hand-reviewed)."""
    hits_all, hits_floor = 0, 0
    for case in FIXTURE["cases"]:
        text = " ".join([case["repo"].split("/")[1].replace("-", " ").replace("_", " "),
                         case["description"] or "", " ".join(case["topics"])])
        got = named(text)
        assert got == case["expected"], (case["repo"], got, case["expected"])
        hits_all += bool(got)
        hits_floor += bool(got) and case["stars"] >= 25
    assert (hits_all, hits_floor) == (16, 10)
    assert named(" ".join(c["description"] or "" for c in FIXTURE["cases"] if c["repo"] == "esp-rs/std-training")) == []
