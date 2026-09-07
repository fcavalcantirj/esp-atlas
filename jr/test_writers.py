"""Tests for jr/writers.py — recipes from resolved signals, additive and cited. All under tmp_path;
the real data/ tree is only read (board socs). Written recipes are validated with the real
recipe schema + the validator's chip check, so what this module writes is what CI accepts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import writers

REPO = Path(__file__).resolve().parent.parent
TODAY = "2026-09-07"
FW_URL = "https://github.com/justcallmekoko/ESP32Marauder"

SIG_ASSET = {"rank": 1, "kind": "asset", "token": "m5cardputer", "soc": None, "line": None,
             "url": "https://github.com/justcallmekoko/ESP32Marauder/releases/download/v1.15.1/esp32_marauder_v1_15_1_20260824_m5cardputer.bin",
             "extra": {"asset": "esp32_marauder_v1_15_1_20260824_m5cardputer.bin", "release": "v1.15.1"}, "how": "compact"}
SIG_PIO = {"rank": 2, "kind": "platformio", "token": "esp32-s3-devkitc-1", "soc": None, "line": 512,
           "url": "https://github.com/wled/WLED/blob/main/platformio.ini#L512", "extra": {"env": "esp32s3dev_8MB_opi", "file": "platformio.ini"}, "how": "compact"}
SIG_CI = {"rank": 3, "kind": "ci", "token": "m5stack-cardputer", "soc": None, "line": None,
          "url": "https://github.com/o/r/blob/main/.github/workflows/build.yml", "extra": {"workflow": ".github/workflows/build.yml"}, "how": "compact"}

SOC = {"m5cardputer": "esp32-s3", "esp32-s3-devkitc-1": "esp32-s3", "lolin-d32": "esp32", "no-soc-board": None}


def _validate(recipe_md: Path, board_soc):
    import jsonschema
    fm = yaml.safe_load(recipe_md.read_text().split("---")[1])
    schema = json.loads((REPO / "schema" / "recipe.schema.json").read_text())
    jsonschema.validate(fm, schema)                                   # schema, additionalProperties false
    assert fm["chip_family"] == board_soc(fm["board"])                # the validator's chip cross-check
    assert fm["id"] == f"{fm['board']}__{fm['firmware']}"
    return fm


def test_render_recipe_is_cited_flashable_and_schema_valid(tmp_path):
    text = writers.render_recipe("m5cardputer__marauder", "m5cardputer", "marauder", "esp32-s3", FW_URL, [SIG_CI, SIG_ASSET], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    fm = _validate(tmp_path / "recipe.md", SOC.get)
    assert fm["status"] == "unverified"
    assert fm["flash"] == {"method": "release-bin", "bin_url": SIG_ASSET["url"]}      # best rank wins
    assert [s["field"] for s in fm["sources"]] == ["*", "board", "board"]
    assert fm["sources"][0]["url"] == FW_URL and fm["sources"][1]["url"] == SIG_ASSET["url"]
    assert all(s["verified"] == TODAY for s in fm["sources"])
    assert "m5cardputer" in fm["notes"] and "release v1.15.1" in fm["notes"] and "not verified on hardware" in fm["notes"]
    assert "- rank 1 asset: `m5cardputer`" in text and "- rank 3 ci: `m5stack-cardputer`" in text


def test_render_recipe_platformio_signal_yields_the_env_not_a_bin(tmp_path):
    text = writers.render_recipe("esp32-s3-devkitc-1__wled", "esp32-s3-devkitc-1", "wled", "esp32-s3", "https://github.com/wled/WLED", [SIG_PIO], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    fm = _validate(tmp_path / "recipe.md", SOC.get)
    assert fm["flash"] == {"env": "esp32s3dev_8MB_opi"}
    assert "(env esp32s3dev_8MB_opi)" in fm["notes"]


def test_render_recipe_without_a_flashable_signal_has_no_flash_block(tmp_path):
    text = writers.render_recipe("m5cardputer__x", "m5cardputer", "x", "esp32-s3", "https://github.com/o/x", [SIG_CI], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    fm = _validate(tmp_path / "recipe.md", SOC.get)
    assert "flash" not in fm


def test_write_recipes_is_additive_cites_and_refuses_chip_clashes(tmp_path):
    root = tmp_path
    (root / "data" / "recipes" / "lolin-d32__marauder").mkdir(parents=True)
    (root / "data" / "recipes" / "lolin-d32__marauder" / "recipe.md").write_text("---\nid: lolin-d32__marauder\nstatus: known-good\n---\nhuman-written\n")
    resolved = {"boards": {
        "m5cardputer": [SIG_ASSET],
        "lolin-d32": [dict(SIG_ASSET, token="lolin_d32")],                        # already has a recipe → untouched
        "esp32-s3-devkitc-1": [dict(SIG_PIO, soc="esp32")],                       # signal says esp32, board is esp32-s3 → refused
        "no-soc-board": [SIG_CI],
    }, "socs": {"esp32-c6": [{"rank": 4, "kind": "idf", "token": "esp32c6"}]}}
    res = writers.write_recipes("marauder", FW_URL, resolved, root=root, today=TODAY, board_soc=SOC.get)
    assert res["written"] == ["m5cardputer__marauder"]
    assert res["paths"] == ["data/recipes/m5cardputer__marauder"]
    assert res["existing"] == ["lolin-d32__marauder"]
    assert res["refused"] == [("esp32-s3-devkitc-1", "signal chip esp32 disagrees with the board's esp32-s3"),
                              ("no-soc-board", "board has no catalogued soc")]
    assert res["socs"] == ["esp32", "esp32-c6", "esp32-s3"]                         # union: existing lolin-d32 (esp32) + written + chip-only
    assert (root / "data/recipes/lolin-d32__marauder/recipe.md").read_text().endswith("human-written\n")
    _validate(root / "data/recipes/m5cardputer__marauder/recipe.md", SOC.get)
    again = writers.write_recipes("marauder", FW_URL, resolved, root=root, today=TODAY, board_soc=SOC.get)
    assert again["written"] == [] and again["existing"] == ["lolin-d32__marauder", "m5cardputer__marauder"]


def test_socs_for_reads_existing_recipes(tmp_path):
    for b in ("m5cardputer", "lolin-d32"):
        (tmp_path / "data" / "recipes" / f"{b}__fw").mkdir(parents=True)
        (tmp_path / "data" / "recipes" / f"{b}__fw" / "recipe.md").write_text("---\n---\n")
    (tmp_path / "data" / "recipes" / "m5cardputer__other").mkdir(parents=True)
    assert writers.socs_for("fw", tmp_path, board_soc=SOC.get) == ["esp32", "esp32-s3"]


FW_MD = """\
---
id: marauder
type: firmware
name: "ESP32 Marauder"
socs:
- esp32
category: pentest
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-08-24'
---

Body with "quotes" and ç stays.
"""


def test_merge_socs_widens_never_narrows_and_cites(tmp_path):
    p = tmp_path / "firmware.md"
    p.write_text(FW_MD)
    assert writers.merge_socs(p, ["esp32-s3", "esp32"], "https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1", TODAY)
    fm = yaml.safe_load(p.read_text().split("---")[1])
    assert fm["socs"] == ["esp32", "esp32-s3"]
    assert fm["sources"][-1] == {"field": "socs", "url": "https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1", "verified": TODAY}
    assert p.read_text().endswith('Body with "quotes" and ç stays.\n')
    assert not writers.merge_socs(p, ["esp32"], "https://x", TODAY)                 # narrower: no change, no citation
    assert not writers.merge_socs(p, ["esp32-s3"], "https://x", TODAY)              # already there
    assert p.read_text().count("field: socs") == 1


def test_merge_socs_handles_an_inline_list_and_a_missing_block(tmp_path):
    p = tmp_path / "firmware.md"
    p.write_text(FW_MD.replace("socs:\n- esp32\n", "socs: [esp32, esp32-c3]\n"))
    assert writers.merge_socs(p, ["esp32-s3"], "https://x", TODAY)
    assert yaml.safe_load(p.read_text().split("---")[1])["socs"] == ["esp32", "esp32-c3", "esp32-s3"]
    q = tmp_path / "fw2.md"
    q.write_text(FW_MD.replace("socs:\n- esp32\n", ""))
    assert writers.merge_socs(q, ["esp32-s3"], "https://x", TODAY)
    fm = yaml.safe_load(q.read_text().split("---")[1])
    assert fm["socs"] == ["esp32-s3"] and fm["name"] == "ESP32 Marauder"
