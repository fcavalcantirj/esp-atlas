"""Every generated FAQ answer must trace to a real, sourced field -- the
build-time guard promoted from spike/faq-c6 (see faq_grounding.py's module
docstring). Runs the real generator over every real soc in data/socs/, plus
a couple of deliberately-broken claims to prove the guard actually fails."""
import pytest

from esp_atlas_core.faq import generate_faq
from esp_atlas_core.faq_grounding import FAQGroundingError, ground_item, ground_items, is_present, resolve, source_covers
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter

C6_FILE = "data/socs/esp32-c6/chip.md"
C3_FILE = "data/socs/esp32-c3/chip.md"


def _all_soc_frontmatters():
    soc_by_id = {}
    for content_type, path in iter_data_files():
        if content_type == "soc":
            fm, _body = parse_frontmatter(path)
            soc_by_id[fm["id"]] = fm
    return soc_by_id


SOC_BY_ID = _all_soc_frontmatters()
SOC_IDS = sorted(SOC_BY_ID)


# --- resolve/is_present/source_covers primitives -----------------------------


def test_resolve_walks_a_dotted_path():
    fm = {"a": {"b": {"c": 1}}}
    assert resolve(fm, "a.b.c") == 1


def test_resolve_missing_path_is_missing_sentinel():
    fm = {"a": {}}
    assert not is_present(fm, "a.b.c")


def test_source_covers_star_covers_everything():
    fm = {"sources": [{"field": "*"}]}
    assert source_covers(fm, "cpu.max_mhz")


def test_source_covers_dotted_prefix():
    fm = {"sources": [{"field": "reserved_pins"}]}
    assert source_covers(fm, "reserved_pins.strapping")
    assert not source_covers(fm, "cpu.max_mhz")


def test_source_covers_no_matching_field():
    fm = {"sources": [{"field": "drive"}]}
    assert not source_covers(fm, "cpu.max_mhz")


# --- the guard, exercised on every real soc's generated FAQ ------------------


@pytest.mark.parametrize("soc_id", SOC_IDS)
def test_generated_faq_is_grounded_for_every_real_soc(soc_id):
    """generate_faq() itself runs the guard -- this just proves it doesn't raise
    for any of the 12 real seeded socs, and that every item still has >=1 claim."""
    items = generate_faq(soc_id, SOC_BY_ID[soc_id], SOC_BY_ID)
    for item in items:
        assert item["claims"], f"{soc_id}:{item['id']} has no grounding claims"


def test_esp32_c6_produces_the_five_expected_items():
    items = generate_faq("esp32-c6", SOC_BY_ID["esp32-c6"], SOC_BY_ID)
    assert [i["id"] for i in items] == ["specs", "gpio-count", "radios", "lp-core", "vs-sibling"]


def test_esp32_c6_vs_sibling_picks_c3_the_most_contrasting_sibling():
    """Not the numerically-nearest (c5, one model number away, is nearly
    spec-identical to c6); the sibling picker maximizes capability contrast
    -- see faq.py's pick_sibling docstring."""
    items = generate_faq("esp32-c6", SOC_BY_ID["esp32-c6"], SOC_BY_ID)
    vs_item = next(i for i in items if i["id"] == "vs-sibling")
    assert "ESP32-C3" in vs_item["question"]


# --- the guard actually fails on ungrounded claims ---------------------------


def test_ground_item_raises_when_claimed_value_does_not_match_real_data():
    item = {
        "id": "bogus",
        "question": "Q?",
        "answer": "The ESP32-C6 runs at up to 999 MHz.",
        "claims": [{"file": C6_FILE, "path": "cpu.max_mhz", "expect": 999, "in_answer": ["999 MHz"]}],
    }
    with pytest.raises(FAQGroundingError):
        ground_item(item)


def test_ground_item_raises_when_field_has_no_covering_source():
    """A record whose `sources` doesn't cover the claimed field can't ground
    an answer, even if the value itself is correct (cite-or-omit)."""
    item = {
        "id": "bogus-uncited",
        "question": "Q?",
        "answer": "The ESP32-C6 runs at up to 160 MHz.",
        "claims": [{"file": C6_FILE, "path": "cpu.max_mhz", "expect": 160, "in_answer": ["160 MHz"]}],
    }
    fm = SOC_BY_ID["esp32-c6"]
    assert resolve(fm, "cpu.max_mhz") == 160  # sanity: the value really is 160

    # Same claim, against a record whose only source doesn't cover cpu.* --
    # proves the guard checks citation coverage, not just value equality.
    from esp_atlas_core import faq_grounding

    original_load = faq_grounding.load_frontmatter
    try:
        faq_grounding.load_frontmatter = lambda relpath: {**fm, "sources": [{"field": "drive"}]}
        with pytest.raises(FAQGroundingError, match="no covering"):
            ground_item(item)
    finally:
        faq_grounding.load_frontmatter = original_load


def test_ground_item_raises_when_phrase_missing_from_answer():
    item = {
        "id": "bogus-phrase",
        "question": "Q?",
        "answer": "The ESP32-C6 has a fast CPU.",
        "claims": [{"file": C6_FILE, "path": "cpu.max_mhz", "expect": 160, "in_answer": ["160 MHz"]}],
    }
    with pytest.raises(FAQGroundingError, match="phrase"):
        ground_item(item)


def test_ground_item_raises_when_path_does_not_resolve():
    item = {
        "id": "bogus-path",
        "question": "Q?",
        "answer": "The ESP32-C6 has a made-up field.",
        "claims": [{"file": C6_FILE, "path": "cpu.does_not_exist", "expect": 1, "in_answer": ["made-up"]}],
    }
    with pytest.raises(FAQGroundingError, match="not found"):
        ground_item(item)


def test_ground_item_absent_kind_raises_when_field_is_actually_present():
    item = {
        "id": "bogus-absent",
        "question": "Q?",
        "answer": "The ESP32-C6 has no CPU.",
        "claims": [{"file": C6_FILE, "path": "cpu", "in_answer": ["no CPU"], "kind": "absent"}],
    }
    with pytest.raises(FAQGroundingError, match="absent"):
        ground_item(item)


def test_ground_item_raises_when_item_has_no_claims():
    item = {"id": "no-claims", "question": "Q?", "answer": "A.", "claims": []}
    with pytest.raises(FAQGroundingError, match="no grounding claims"):
        ground_item(item)


def test_ground_items_stops_at_the_first_ungrounded_item():
    good = generate_faq("esp32-c6", SOC_BY_ID["esp32-c6"], SOC_BY_ID)[:1]
    bad = [{
        "id": "bogus",
        "question": "Q?",
        "answer": "The ESP32-C6 runs at up to 999 MHz.",
        "claims": [{"file": C6_FILE, "path": "cpu.max_mhz", "expect": 999, "in_answer": ["999 MHz"]}],
    }]
    with pytest.raises(FAQGroundingError):
        ground_items(good + bad)
