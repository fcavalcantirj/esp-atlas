"""Template behavior for esp_atlas_core.faq -- what each item says and when a
template is (or isn't) applicable, over the real seeded data/socs/ dataset.
Grounding itself is covered by test_faq_grounding.py."""
import pytest

from esp_atlas_core.faq import _series_key, build_faq_items, faq_text, generate_faq, pick_sibling, public_items
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter


def _all_soc_frontmatters():
    soc_by_id = {}
    for content_type, path in iter_data_files():
        if content_type == "soc":
            fm, _body = parse_frontmatter(path)
            soc_by_id[fm["id"]] = fm
    return soc_by_id


SOC_BY_ID = _all_soc_frontmatters()


def _items(soc_id):
    return generate_faq(soc_id, SOC_BY_ID[soc_id], SOC_BY_ID)


def _answer(items, item_id):
    return next(i["answer"] for i in items if i["id"] == item_id)


# --- specs -------------------------------------------------------------------


def test_specs_item_mentions_headline_numbers_for_esp32_c6():
    answer = _answer(_items("esp32-c6"), "specs")
    for phrase in ("single-core", "RISC-V", "up to 160 MHz", "512 KB of SRAM", "Wi-Fi 6", "Bluetooth LE 5.3"):
        assert phrase in answer


def test_specs_item_says_no_wifi_when_wifi_is_null():
    answer = _answer(_items("esp32-h2"), "specs")
    assert "no Wi-Fi radio" in answer


def test_specs_item_omits_usb_clause_gracefully_when_native_true():
    answer = _answer(_items("esp32-c3"), "specs")
    assert "native USB" in answer


# --- gpio-count ----------------------------------------------------------------


def test_gpio_count_item_present_for_esp32_c6():
    answer = _answer(_items("esp32-c6"), "gpio-count")
    assert "30 GPIO pads" in answer
    assert "5 are strapping pins" in answer
    assert "2 are tied to USB/flash" in answer


def test_gpio_count_item_question_mentions_pinout():
    """The home-search demand term is "pinout" -- see REPORT.md (d) /
    test_faq_fts.py. The question text is what makes the term findable."""
    items = _items("esp32-c6")
    question = next(i["question"] for i in items if i["id"] == "gpio-count")
    assert "pinout" in question


def test_gpio_count_item_degrades_when_no_reserved_pins_data():
    """esp32-h4 has drive.gpio_pads_total but no reserved_pins block at all --
    cite-or-omit at the clause level, not a guessed strapping count."""
    answer = _answer(_items("esp32-h4"), "gpio-count")
    assert "40 GPIO pads in total." == answer.split("The ESP32-H4 has ")[1]
    assert "strapping" not in answer


def test_gpio_count_item_absent_when_no_drive_spec():
    items = build_faq_items("no-drive-spec", {**SOC_BY_ID["esp32-c6"], "drive": None}, SOC_BY_ID)
    assert "gpio-count" not in [i["id"] for i in items]


# --- radios --------------------------------------------------------------------


def test_radios_item_lists_protocols_for_esp32_c6():
    answer = _answer(_items("esp32-c6"), "radios")
    assert "Wi-Fi 6 radio" in answer
    assert "Bluetooth LE 5.3" in answer
    assert "zigbee-3.0, thread-1.3, matter" in answer


def test_radios_item_says_no_802154_when_absent():
    answer = _answer(_items("esp32-c3"), "radios")
    assert "no 802.15.4 radio" in answer


def test_radios_item_says_no_bluetooth_when_null():
    answer = _answer(_items("esp32-s2"), "radios")
    assert "no Bluetooth radio" in answer


# --- lp-core ---------------------------------------------------------------------


def test_lp_core_item_yes_for_esp32_c6():
    answer = _answer(_items("esp32-c6"), "lp-core")
    assert answer.startswith("Yes")
    assert "up to 20 MHz" in answer


def test_lp_core_item_no_for_esp32_c3():
    answer = _answer(_items("esp32-c3"), "lp-core")
    assert answer.startswith("No")
    assert "no separate low-power (LP) core" in answer


# --- vs-sibling / series grouping ------------------------------------------------


def test_series_key_groups_by_letter_prefix():
    assert _series_key("esp32-c6") == "c"
    assert _series_key("esp32-c61") == "c"
    assert _series_key("esp32-s31") == "s"
    assert _series_key("esp32") is None
    assert _series_key("esp32-p4") == "p"


def test_pick_sibling_none_for_a_series_of_one():
    assert pick_sibling("esp32-p4", SOC_BY_ID["esp32-p4"], SOC_BY_ID) is None
    assert pick_sibling("esp32", SOC_BY_ID["esp32"], SOC_BY_ID) is None


def test_vs_sibling_item_absent_when_no_sibling_exists():
    items = _items("esp32-p4")
    assert "vs-sibling" not in [i["id"] for i in items]


def test_vs_sibling_item_present_and_names_both_chips_for_esp32_c6():
    answer = _answer(_items("esp32-c6"), "vs-sibling")
    assert "The ESP32-C6 is a" in answer
    assert "the ESP32-C3 is a" in answer
    assert "Wi-Fi 6 vs Wi-Fi 4" in answer
    assert "LP core yes vs LP core no" in answer


# --- faq_text / public_items --------------------------------------------------


def test_faq_text_concatenates_every_question_and_answer():
    items = _items("esp32-c6")
    text = faq_text(items)
    for item in items:
        assert item["question"] in text
        assert item["answer"] in text


def test_public_items_strips_claims():
    items = _items("esp32-c6")
    public = public_items(items)
    assert all(set(i) == {"id", "question", "answer"} for i in public)
    assert [i["id"] for i in public] == [i["id"] for i in items]


def test_faq_text_empty_for_empty_items():
    assert faq_text([]) == ""


# --- cite-or-omit at the whole-record level ------------------------------------


def test_build_faq_items_empty_when_cpu_or_memory_missing():
    """A soc record without cpu/memory (schema-required, but a minimal test
    fixture elsewhere in the suite doesn't carry them) gets no FAQ rather
    than a template crashing on a missing key."""
    assert build_faq_items("fake-soc", {"id": "fake-soc", "name": "Fake SoC"}, {}) == []
