"""jr/autoreview.py against the labelled history (SPEC-jr-review-routing.md §7): every known-wrong edge
(the originals preserved in jr/overrides/*__edges.json) must not PASS; every edge both blind audits
agreed is correct must not FAIL."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import autoreview
import board_alias

CASES = json.loads((Path(__file__).parent / "fixtures" / "autoreview" / "cases.json").read_text())


@pytest.fixture(scope="module")
def catalog():
    board_alias.clear_caches()
    return board_alias.atlas_boards()


def _sources(c):
    return {"description": c["description"], "readme": "\n".join(c["readme_lines"]), "platformio": c["platformio"],
            "assets": " ".join(c.get("assets") or [])}


@pytest.mark.parametrize("case", [c for c in CASES if c["label"] == "wrong"], ids=lambda c: f"{c['board']}__{c['firmware']}")
def test_a_known_wrong_edge_never_passes(case, catalog):
    v = autoreview.check(case["board"], _sources(case), catalog)
    assert v.verdict != autoreview.PASS, v.reasons


@pytest.mark.parametrize("case", [c for c in CASES if c["label"] == "correct"], ids=lambda c: f"{c['board']}__{c['firmware']}")
def test_a_known_correct_edge_never_fails(case, catalog):
    v = autoreview.check(case["board"], _sources(case), catalog)
    assert v.verdict != autoreview.FAIL, v.reasons


def test_no_source_is_uncertain_never_a_guess(catalog):
    assert autoreview.check("m5cardputer", {}, catalog).verdict == autoreview.UNCERTAIN


# --- each rule on its own ---------------------------------------------------------------------------

def _v(board, catalog, **src):
    return autoreview.check(board, src, catalog)


def test_named_the_board_passes_and_silence_fails(catalog):
    assert _v("m5cardputer", catalog, description="A synth for the M5Stack Cardputer").verdict == autoreview.PASS
    assert _v("m5cardputer", catalog, description="A synth for the XIAO ESP32-S3").verdict == autoreview.FAIL


def test_a_library_or_url_is_not_a_mention_of_the_board(catalog):
    v = _v("m5cardputer", catalog, readme="#include <M5Cardputer.h>\nSee https://github.com/m5stack/M5Cardputer\nRuns on the T-Deck")
    assert v.verdict == autoreview.FAIL


def test_only_the_sibling_named_fails(catalog):
    v = _v("m5cardputer", catalog, description="Offline map for Cardputer ADV")
    assert v.verdict == autoreview.FAIL and "Cardputer ADV" in v.reasons[0]


def test_sibling_plus_a_generic_mention_is_uncertain(catalog):
    v = _v("m5cardputer", catalog, description="for the M5Stack Cardputer", readme="Flash it to your Cardputer ADV")
    assert v.verdict == autoreview.UNCERTAIN


def test_the_pair_named_side_by_side_passes(catalog):
    assert _v("m5cardputer", catalog, readme="Runs on the Cardputer and Cardputer ADV").verdict == autoreview.PASS
    assert _v("m5cardputer", catalog, readme="Supported: Cardputer ADV / original Cardputer").verdict == autoreview.PASS


def test_separate_builds_for_both_pass(catalog):
    assert _v("m5cardputer", catalog, readme="Cardputer ADV build", assets="fw-cardputer.bin fw-cardputer-adv.bin").verdict == autoreview.PASS


def test_a_question_about_the_original_is_not_support(catalog):
    v = _v("m5cardputer", catalog, readme="Built for the Cardputer ADV.\n**Can I use the original Cardputer?**\nThe Cardputer sends it")
    assert v.verdict == autoreview.UNCERTAIN


def test_adv_only_against_the_original_fails_but_a_feature_note_does_not(catalog):
    assert _v("m5cardputer", catalog, readme="**Cardputer ADV only** — the original Cardputer has a different keyboard").verdict == autoreview.FAIL
    assert _v("m5cardputer", catalog, readme="Runs on the Cardputer and Cardputer ADV.\nGyro: gx, gy (Cardputer ADV only)").verdict == autoreview.PASS


def test_the_original_said_unsupported_fails(catalog):
    assert _v("m5cardputer", catalog, readme="For the Cardputer ADV. The original Cardputer is not supported.").verdict == autoreview.FAIL


def test_a_negated_mention_is_uncertain(catalog):
    assert _v("m5stick-s3", catalog, readme="This doesn't run on the StickS3 yet").verdict == autoreview.UNCERTAIN


def test_carrier_module_under_a_product_env_fails_and_a_module_env_passes(catalog):
    product = "[env:cardputer]\nboard = m5stack-stamps3\nlib_deps = m5stack/M5Cardputer\n"
    assert _v("m5stamp-s3", catalog, platformio=product, readme="Cardputer (M5Stack StampS3)").verdict == autoreview.FAIL
    module = product + "[env:stamps3]\nboard = m5stack-stamps3\n"
    assert _v("m5stamp-s3", catalog, platformio=module).verdict == autoreview.PASS


# --- DasBrow's adversarial review of #1722 (room 12156): 7 inputs that read as PASS -----------------

@pytest.mark.parametrize("text", [
    "Firmware for the M5Stack Cardputer (ADV). Uses the TCA8418 keyboard.",
    "Runs on the ADV Cardputer only.",
    "Built for the Cardputer Advanced edition.",
], ids=["adv-in-parens", "adv-before", "advanced"])
def test_adv_phrasings_never_pass_as_the_original(text, catalog):
    assert _v("m5cardputer", catalog, description=text).verdict in (autoreview.FAIL, autoreview.UNCERTAIN)


@pytest.mark.parametrize("text", [
    "Ported from the Cardputer version; this build runs on the LilyGO T-Deck.",
    "Supported: T-Deck. Planned: Cardputer",
    "Inspired by the M5Stack Cardputer launcher, for the T-Display S3.",
    "Requires Cardputer v2 hardware (the new keyboard).",
], ids=["ported-from", "planned", "inspired-by", "unknown-version"])
def test_a_mention_that_is_not_a_target_is_uncertain(text, catalog):
    assert _v("m5cardputer", catalog, description=text).verdict == autoreview.UNCERTAIN


def test_a_target_mention_beside_a_provenance_one_still_passes(catalog):
    v = _v("m5cardputer", catalog, readme="Inspired by M5Launcher. Runs on the M5Stack Cardputer.")
    assert v.verdict == autoreview.PASS


def test_adv_in_parentheses_alone_is_the_adv(catalog):
    assert _v("m5cardputer", catalog, description="Firmware for the M5Stack Cardputer (ADV).").verdict == autoreview.FAIL


def test_the_adv_keyboard_chip_alone_marks_the_adv(catalog):
    assert _v("m5cardputer", catalog, description="Cardputer firmware. Uses the TCA8418 keyboard.").verdict == autoreview.UNCERTAIN


def test_a_build_env_for_the_board_is_a_target_even_when_prose_says_ported_from(catalog):
    v = _v("m5cardputer", catalog, readme="Ported from the Cardputer version.", platformio="[env:cardputer]\nboard = m5stack-stamps3\n")
    assert v.verdict == autoreview.PASS


# --- DasBrow's review of #1722 @180e2c70 (room 12192) --------------------------------------------------

@pytest.mark.parametrize("text", ["Firmware for the Cardputer [ADV] edition.", "Firmware for the Cardputer {ADV}."],
                         ids=["brackets", "braces"])
def test_adv_in_any_bracket_is_the_adv(text, catalog):
    assert _v("m5cardputer", catalog, description=text).verdict == autoreview.FAIL


def test_an_untested_original_is_a_caveat_not_support(catalog):
    v = _v("m5cardputer", catalog, description="Requires Cardputer ADV; the original Cardputer is untested.")
    assert v.verdict == autoreview.UNCERTAIN


def test_an_untested_caveat_beside_explicit_support_still_passes(catalog):
    """c-p-s (labelled correct): "Supported devices | M5Stack CardputerADV, original Cardputer" AND "Original
    Cardputer support hasn't been verified on real hardware by the developer yet"."""
    readme = ("| Supported devices | M5Stack CardputerADV, original Cardputer (auto-detected at boot) |\n"
              "- Original Cardputer support hasn't been verified on real hardware by the developer yet")
    assert _v("m5cardputer", catalog, readme=readme).verdict == autoreview.PASS


# --- v2 rules, from the real correct edges the v1 checker left UNCERTAIN ----------------------------

def test_separate_rows_for_the_original_and_the_adv_are_explicit(catalog):
    readme = "| Device | Status |\n| M5Cardputer    | ✅ Supported |\n| M5Cardputer adv| ✅ Supported |"
    assert _v("m5cardputer", catalog, readme=readme).verdict == autoreview.PASS
    rows = "| **M5Stack Cardputer ADV** | ESP32-S3 |\n| **M5Stack Cardputer** | ESP32-S3 |"
    assert _v("m5cardputer", catalog, readme=rows).verdict == autoreview.PASS


def test_original_m5stack_cardputer_is_explicit(catalog):
    v = _v("m5cardputer", catalog, readme="NucleoOS runs on both the original M5Stack Cardputer and the newer Cardputer ADV")
    assert v.verdict == autoreview.PASS


def test_a_negation_not_about_support_is_not_a_doubt(catalog):
    v = _v("m5cardputer", catalog, readme="Runs on the Cardputer and Cardputer ADV.\nThe key goes to the provider — the Cardputer isn't in the loop.")
    assert v.verdict == autoreview.PASS


def test_feature_level_adv_only_notes_imply_the_original(catalog):
    v = _v("m5cardputer", catalog, readme="Embedded bytebeats for Cardputer\n+ Accelerometer: ax, ay, az (Cardputer ADV only)")
    assert v.verdict == autoreview.PASS


def test_a_separate_adv_branch_means_the_default_build_is_the_original(catalog):
    v = _v("m5cardputer", catalog, readme="M5Cardputer user demo.\nIf you are using Cardputer ADV, please use the CardputerADV branch.")
    assert v.verdict == autoreview.PASS


def test_v2_still_refuses_the_adv_only_shapes(catalog):
    assert _v("m5cardputer", catalog, readme="| Device |\n| M5Cardputer ADV | ✅ |").verdict == autoreview.FAIL
    assert _v("m5cardputer", catalog, readme="Firmware for the Cardputer ADV.\nGyro: gx (ADV only)").verdict == autoreview.FAIL


def test_a_bold_board_name_is_not_a_device_row(catalog):
    """WebRadio_WuSiU_Cardputer_Adv (#1715): its README tells Arduino users to pick the board definition
    `**M5Cardputer**`. Bold text starts with '*' but is not a list item; only '- ', '* ', '+ ' or '|' are."""
    readme = ("# Cardputer Adv WebRadio\nAn internet radio for **M5Stack Cardputer Adv**.\n"
              "- M5Stack Cardputer Adv\nChoose the correct board for Cardputer:\n**M5Cardputer**\n")
    assert _v("m5cardputer", catalog, description="WebRadio adapted for Caedputer ADV", readme=readme).verdict != autoreview.PASS


def test_not_the_original_is_an_exclusion(catalog):
    """SquachWatch-CYD's support table (#1728): 'M5Stack Cardputer ADV | BETA | ... Not the original Cardputer.'"""
    row = "| M5Stack Cardputer ADV | BETA | Driven from its keyboard, with hotkeys. Not the original Cardputer. SD card |"
    assert _v("m5cardputer", catalog, readme=row).verdict == autoreview.FAIL


def test_first_gen_cardputer_is_explicit_original_support(catalog):
    """M5MonsterC5-CardputerADV (#1729): 'App for the M5Stack Cardputer AVD and for first gen Cardputer'."""
    v = _v("m5cardputer", catalog, readme="- App for the M5Stack Cardputer ADV and for first gen Cardputer - flasher")
    assert v.verdict == autoreview.PASS


def test_a_library_link_with_a_framework_word_is_not_a_device_row(catalog):
    """cardputer-adv-uhf-expansion (#1747): an ADV-only README whose 'Links' list carries
    '- [M5Cardputer Arduino library](...)'. The library shares the board's name; v2 read the list item as a
    device row beside the '| Cardputer ADV |' table and PASSed the original Cardputer."""
    readme = ("Firmware for the **M5Stack Cardputer ADV**.\n| Cardputer ADV | Firmware function |\n"
              "- [M5Cardputer Arduino library](https://github.com/m5stack/M5Cardputer)\n")
    assert _v("m5cardputer", catalog, description="Cardputer ADV firmware", readme=readme).verdict == autoreview.FAIL
    for ref in ("M5Cardputer PlatformIO library", "the M5Cardputer SDK", "M5Cardputer libraries", "M5Cardputer ESP-IDF component"):
        v = _v("m5cardputer", catalog, readme=f"Runs on the T-Deck.\n- {ref}\n")
        assert v.verdict == autoreview.FAIL, (ref, v.reasons)


# --- v4 (2026-11-19, tick PR #1828, m5cardputer__m5-crystal): a gloss attached to the sibling is not the original --
# Upstream README: "Devices: M5StickCPlus2, M5StickS3, Cardputer-ADV (Cardputer v1.1)"; its only Cardputer build
# is [env:cardputer-adv]. v3 read "(Cardputer v1.1)" as an explicit mention of the original and PASSed it.

CRYSTAL_README = "- Devices: M5StickCPlus2, M5StickS3, Cardputer-ADV (Cardputer v1.1)\n- [x] M5 Stick S3 support\n"
CRYSTAL_PIO = ("[env:m5stick-c-plus2]\nboard = m5stickc_plus2\n[env:m5sticks3]\nboard = esp32-s3-devkitc-1\n"
               "[env:cardputer-adv]\nboard = esp32-s3-devkitc-1\nbuild_flags =\n\t-DSTICKS3\n\t-DCARDPUTER\n")


def test_a_parenthetical_gloss_on_the_sibling_does_not_prove_the_original(catalog):
    v = _v("m5cardputer", catalog, readme=CRYSTAL_README, platformio=CRYSTAL_PIO)
    assert v.verdict == autoreview.UNCERTAIN and "sibling" in v.reasons[0], v
    assert _v("m5cardputer-adv", catalog, readme=CRYSTAL_README, platformio=CRYSTAL_PIO).verdict == autoreview.PASS


def test_a_parenthetical_that_adds_the_original_with_a_conjunction_still_counts(catalog):
    for line in ("Runs on the Cardputer-ADV (and the original Cardputer)", "Cardputer ADV (also Cardputer v1.1)",
                 "Cardputer-ADV (or Cardputer v1.0 / v1.1)"):
        assert _v("m5cardputer", catalog, readme=line).verdict == autoreview.PASS, line


def test_the_gloss_rule_leaves_a_separate_explicit_mention_alone(catalog):
    readme = "Devices: Cardputer-ADV (Cardputer v1.1)\nAlso tested on the original Cardputer."
    assert _v("m5cardputer", catalog, readme=readme).verdict == autoreview.PASS


def test_the_rules_version_is_4():
    assert autoreview.RULES_VERSION == "4"
