"""M5Stack Cardputer-Adv is its own catalogued board (m5cardputer-adv), not the original Cardputer.

docs.m5stack.com/en/core/Cardputer-Adv: a Stamp-S3A with a TCA8418 I2C keyboard (G8/G9/G11), ES8311,
BMI270, 3.5 mm jack, EXT 2.54-14P; the original K132 scans a GPIO key matrix. Firmware written for one
keyboard does not drive the other, so text that names ONLY the ADV maps to the ADV, and any plain
"Cardputer" mention (including "Cardputer & ADV") keeps the original, which that firmware also supports.
"""
from __future__ import annotations

import pytest

import board_alias
import board_doc_resolvers
import derive
import device_map


@pytest.mark.parametrize("text,expected", [
    ("Cardputer ADV", "m5cardputer-adv"),
    ("Meshcore for Cardputer-Adv", "m5cardputer-adv"),
    ("daoa-mini-cardputeradv", "m5cardputer-adv"),
    ("M5Cardputer-ADV Wi-Fi radar", "m5cardputer-adv"),
    ("cardputer_adv build", "m5cardputer-adv"),
    ("Cardputer", "m5cardputer"),
    ("M5Stack Cardputer", "m5cardputer"),
    ("Cardputer & ADV", "m5cardputer"),
    ("Cardputer / Cardputer-ADV", "m5cardputer"),
    ("for the Cardputer and the Cardputer ADV", "m5cardputer"),
    ("Cardputer AdvanceOS", "m5cardputer"),
    ("advanceos-for-cardputer", "m5cardputer"),
    ("Cardputer Adventure", "m5cardputer"),
    ("cardputer-advanced-tools", "m5cardputer"),
], ids=["adv-space", "adv-hyphen", "adv-fused", "m5-adv", "adv-underscore", "plain", "m5-plain",
       "plain-and-adv", "plain-slash-adv", "plain-then-adv", "advanceos", "advanceos-slug", "adventure",
       "advanced"])
def test_device_from_text_separates_the_adv_from_the_original(text, expected):
    assert device_map.device_from_text(text) == expected


def test_the_name_still_wins_over_the_description():
    assert device_map.device_from_text("Radar for Cardputer ADV", "works on any Cardputer") == "m5cardputer-adv"
    assert device_map.device_from_text("Tool for Cardputer", "also on the Cardputer ADV") == "m5cardputer"


def test_the_launcher_category_cardputer_adv_is_unambiguous():
    assert device_map.CATEGORY_BOARD_FALLBACK["cardputer-adv"] == "m5cardputer-adv"
    assert device_map.CATEGORY_BOARD_FALLBACK["cardputer"] == "m5cardputer"


def test_the_board_doc_path_is_the_official_page():
    assert board_doc_resolvers.M5STACK_DOC_PATHS["m5cardputer-adv"] == "core/Cardputer-Adv"


@pytest.fixture
def real_catalog():
    board_alias.clear_caches()
    return board_alias.atlas_boards()


def test_the_board_is_catalogued(real_catalog):
    b = real_catalog["m5cardputer-adv"]
    assert b["soc"] == "esp32-s3" and b["name"] == "Cardputer-Adv"


def test_a_cardputer_adv_env_on_the_stamp_module_names_the_adv(real_catalog):
    """daoa-mini declares `[env:cardputer-adv] board = m5stack-stamps3`: the env names the product."""
    base = {"rank": 2, "kind": "platformio", "token": "m5stack-stamps3", "url": "u", "soc": None, "line": 1}
    r = derive.resolve({"signals": [dict(base, extra={"env": "cardputer-adv", "file": "platformio.ini"}),
                                    dict(base, extra={"env": "cardputer", "file": "platformio.ini"})]},
                       boards=real_catalog)
    assert {s["extra"]["env"] for s in r["boards"]["m5cardputer-adv"]} == {"cardputer-adv"}
    assert {s["extra"]["env"] for s in r["boards"]["m5cardputer"]} == {"cardputer"}
