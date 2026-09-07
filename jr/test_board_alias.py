"""Tests for jr/board_alias.py — deterministic universe/token → atlas board resolution.

Fixture tests use hand-made boards/entries/aliases (no repo data). Two tests read the REAL
tree (data/boards + data/board_universe.json) to pin coverage and the zero-wrong-chip rule.

Run: cd jr && python3 -m pytest test_board_alias.py -v
"""
from __future__ import annotations

import pytest

import board_alias as ba

BOARDS = {
    "m5cardputer": {"id": "m5cardputer", "name": "M5Cardputer", "aka": [], "soc": "esp32-s3", "brand": "m5stack"},
    "m5stick-cplus2": {"id": "m5stick-cplus2", "name": "M5StickC Plus2", "aka": [], "soc": "esp32-s3", "brand": "m5stack"},
    "lilygo-t-deck": {"id": "lilygo-t-deck", "name": "T-Deck", "aka": [], "soc": "esp32-s3", "brand": "lilygo"},
    "lolin-s3-mini": {"id": "lolin-s3-mini", "name": "LOLIN S3 Mini", "aka": ["S3 Mini"], "soc": "esp32-s3", "brand": "wemos"},
    "esp32-devkitc-v4": {"id": "esp32-devkitc-v4", "name": "ESP32-DevKitC V4", "aka": [], "soc": "esp32", "brand": "espressif"},
    "twin-a": {"id": "twin-a", "name": "Twin Board", "aka": [], "soc": "esp32", "brand": "x"},
    "twin-b": {"id": "twin-b", "name": "Twin Board", "aka": [], "soc": "esp32", "brand": "y"},
}


def E(key, name, soc, variant=None, line=None):
    src, bid = key.split(":", 1)
    e = {"key": key, "source": src, "id": bid, "name": name, "soc": soc, "variant": variant,
         "url": f"https://example.invalid/{src}"}
    if line:
        e["line"] = line
    return e


ENTRIES = [
    E("arduino-esp32:m5stack_cardputer", "M5Cardputer", "esp32-s3", "m5stack_cardputer", line=25887),
    E("arduino-esp32:m5stack_stickc_plus2", "M5StickCPlus2", "esp32-s3", "m5stack_stickc_plus2", line=100),
    E("arduino-esp32:lilygo_t_deck_v1", "LilyGo T-Deck (16MB)", "esp32-s3", "lilygo_t_deck_v1", line=200),   # only containment fits
    E("pioarduino:lolin_s3_mini", "WEMOS LOLIN S3 Mini", "esp32-s3", "lolin_s3_mini"),
    E("arduino-esp32:esp32", "ESP32 Dev Module", "esp32", "esp32", line=1),
    E("arduino-esp32:wrong_chip_cardputer", "M5Cardputer", "esp32", "x", line=300),      # same name, other chip
    E("arduino-esp32:twin", "Twin Board", "esp32", "twin", line=400),                    # two atlas boards claim it
    E("arduino-esp32:nochip", "Mystery", None, None, line=500),
]
ALIASES = {"arduino-esp32:esp32": {"atlas_id": "esp32-devkitc-v4", "why": "the generic Dev Module IS the DevKitC"}}


def test_compact_and_chip_only():
    assert ba.compact("M5StickC Plus2") == "m5stickcplus2" == ba.compact("M5StickCPlus2")
    assert ba.compact("  ") == "" and ba.compact(None) == ""
    assert ba.chip_only("esp32-s3") == "esp32-s3" == ba.chip_only("ESP32S3") == ba.chip_only("esp32s3")
    assert ba.chip_only("esp32-s3-devkitc-1") is None


def test_compact_equality_resolves_ids_names_variants_and_aka():
    r = ba.resolve_entry(ENTRIES[0], BOARDS, {})
    assert r == {"atlas_id": "m5cardputer", "how": "compact",
                 "evidence": {"key": "arduino-esp32:m5stack_cardputer", "url": "https://example.invalid/arduino-esp32", "line": 25887}}
    assert ba.resolve_entry(ENTRIES[1], BOARDS, {})["atlas_id"] == "m5stick-cplus2"      # "M5StickCPlus2" vs "M5StickC Plus2"
    assert ba.resolve_entry(ENTRIES[3], BOARDS, {})["atlas_id"] == "lolin-s3-mini"       # via id / aka


def test_containment_resolves_a_brand_prefixed_name_only_when_unique():
    r = ba.resolve_entry(ENTRIES[2], BOARDS, {})
    assert r["atlas_id"] == "lilygo-t-deck" and r["how"] == "contain"


@pytest.mark.parametrize("entry_name,expect", [
    ("LilyGo T-Deck", "lilygo-t-deck"),            # vendor prefix
    ("TTGO T-Deck", "lilygo-t-deck"),              # vendor alias prefix
    ("T-Deck N16R8", "lilygo-t-deck"),             # memory SKU suffix
    ("T-Deck 16MB", "lilygo-t-deck"),
    ("RYMCU T-Deck", None),                        # foreign vendor = clone
    ("T-Deck Pro", None),                          # product suffix = sibling
    ("T-Deck V2", None),                           # revision = sibling
    ("M5Stack T-Deck", None),                      # another catalogued vendor
])
def test_containment_accepts_only_vendor_prefixes_and_memory_suffixes(entry_name, expect):
    e = E("arduino-esp32:x_" + ba.compact(entry_name), entry_name, "esp32-s3", "x", line=1)
    r = ba.resolve_entry(e, BOARDS, {})
    assert (r["atlas_id"] if r else None) == expect


def test_a_name_match_with_a_different_chip_is_refused():
    assert ba.resolve_entry(ENTRIES[5], BOARDS, {}) is None


def test_an_ambiguous_match_is_refused_not_guessed():
    assert ba.resolve_entry(ENTRIES[6], BOARDS, {}) is None


def test_no_chip_means_no_resolution():
    assert ba.resolve_entry(ENTRIES[7], BOARDS, {}) is None


def test_explicit_alias_wins_but_still_needs_soc_agreement():
    r = ba.resolve_entry(ENTRIES[4], BOARDS, ALIASES)
    assert r["atlas_id"] == "esp32-devkitc-v4" and r["how"] == "alias"
    bad = {"arduino-esp32:esp32": {"atlas_id": "m5cardputer", "why": "wrong"}}   # esp32 vs esp32-s3
    assert ba.resolve_entry(ENTRIES[4], BOARDS, bad) is None
    missing = {"arduino-esp32:esp32": {"atlas_id": "does-not-exist", "why": "typo"}}
    assert ba.resolve_entry(ENTRIES[4], BOARDS, missing) is None


def test_build_table_and_report_count_only_resolved_entries():
    table = ba.build_table(BOARDS, ENTRIES, ALIASES)
    assert set(table) == {"arduino-esp32:m5stack_cardputer", "arduino-esp32:m5stack_stickc_plus2",
                          "arduino-esp32:lilygo_t_deck_v1", "pioarduino:lolin_s3_mini", "arduino-esp32:esp32"}
    rep = ba.report(BOARDS, ENTRIES, ALIASES)
    assert rep["resolved"] == 5 and rep["unresolved"] == ["twin-a", "twin-b"]
    assert rep["by_rule"] == {"compact": 3, "contain": 1, "alias": 1}


def test_resolve_token_maps_build_signal_tokens_and_chips():
    assert ba.resolve_token("m5stack_cardputer", boards=BOARDS, entries=ENTRIES, aliases=ALIASES)["atlas_id"] == "m5cardputer"
    assert ba.resolve_token("M5Cardputer", soc="esp32-s3", boards=BOARDS, entries=ENTRIES, aliases=ALIASES)["atlas_id"] == "m5cardputer"
    assert ba.resolve_token("M5Cardputer", soc="esp32", boards=BOARDS, entries=ENTRIES, aliases=ALIASES) is None
    assert ba.resolve_token("esp32s3", boards=BOARDS, entries=ENTRIES) == {"soc": "esp32-s3"}
    assert ba.resolve_token("esp32", boards=BOARDS, entries=ENTRIES, aliases=ALIASES) == {"soc": "esp32"}   # chip wins over the alias
    assert ba.resolve_token("twin", boards=BOARDS, entries=ENTRIES) is None
    assert ba.resolve_token("", boards=BOARDS, entries=ENTRIES) is None
    # a token no universe entry carries still resolves DIRECTLY against the catalog (release
    # asset names use short forms), chip-checked, unambiguous only
    assert ba.resolve_token("T-Deck", boards=BOARDS, entries=ENTRIES)["how"] == "direct"
    assert ba.resolve_token("tdeck", soc="esp32-s3", boards=BOARDS, entries=ENTRIES)["atlas_id"] == "lilygo-t-deck"
    assert ba.resolve_token("tdeck", soc="esp32", boards=BOARDS, entries=ENTRIES) is None
    assert ba.resolve_token("Twin Board", boards=BOARDS, entries=ENTRIES) is None       # two boards share the name


# --- the real tree ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_report():
    ba.clear_caches()
    return ba.report()


def test_real_tree_coverage_never_regresses(real_report):
    """Measured 2026-09-07 before aka landed: compact 91 + containment 15 + alias 13 → 66 of 82.
    Once `aka` is written the containment hits become compact hits (an aka IS a compact key),
    so `by_rule` shifts toward compact; the board count is what must not regress. The 16
    unresolved are absent from both registries or only present as clones/siblings that
    containment refuses on purpose (Inkplate ×4, LilyGO T-Deck/T-Embed/T-Dongle/T-QT/
    T-Display-AMOLED, M5 StickS3 / AtomS3-Lite, Espressif DevKitC-V4 (only an AZ-Delivery clone
    upstream), LyraT, Ethernet-Kit, DevKitM-1, S2-DevKitC-1). Lower the bound with a written reason."""
    assert real_report["atlas_boards"] >= 82
    assert real_report["resolved"] >= 66, real_report["unresolved"]
    assert real_report["by_rule"].get("alias", 0) >= 13


def test_every_explicit_alias_points_at_a_real_universe_entry_and_a_real_board_with_the_same_chip():
    boards, uni = ba.atlas_boards(), {e["key"]: e for e in ba.universe()}
    for key, alias in ba.explicit_aliases().items():
        assert key in uni, f"alias key {key} is not in data/board_universe.json"
        assert alias["atlas_id"] in boards, f"{key} → {alias['atlas_id']} is not a catalogued board"
        assert uni[key]["soc"] == boards[alias["atlas_id"]]["soc"], f"{key}: chip family mismatch"
        assert alias.get("why"), f"{key}: an alias needs a why"


def test_real_tree_never_maps_across_chip_families(real_report):
    boards, uni = ba.atlas_boards(), {e["key"]: e for e in ba.universe()}
    for atlas_id, hits in real_report["by_board"].items():
        for key, _ in hits:
            assert uni[key]["soc"] == boards[atlas_id]["soc"], (atlas_id, key)
