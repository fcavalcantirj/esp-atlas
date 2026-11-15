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
