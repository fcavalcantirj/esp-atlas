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
RELEASE_PAGE = "https://github.com/justcallmekoko/ESP32Marauder/releases/tag/v1.15.1"

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


def test_evidence_url_is_the_release_page_for_an_asset_and_the_signal_url_otherwise():
    assert writers.evidence_url(SIG_ASSET) == RELEASE_PAGE
    assert writers.evidence_url(SIG_PIO) == SIG_PIO["url"]
    assert writers.evidence_url({"kind": "manifest", "url": "https://github.com/o/r/releases/download/v1/manifest.json"}) \
        == "https://github.com/o/r/releases/download/v1/manifest.json"       # a JSON a reader can open: cite it as is
    assert writers.evidence_url({"kind": "asset", "url": "https://cdn.example/x.bin"}) == "https://cdn.example/x.bin"


def test_render_recipe_cites_the_release_page_never_promises_a_bin_url_and_is_schema_valid(tmp_path):
    text = writers.render_recipe("m5cardputer__marauder", "m5cardputer", "marauder", "esp32-s3", FW_URL, [SIG_CI, SIG_ASSET], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    fm = _validate(tmp_path / "recipe.md", SOC.get)
    assert fm["status"] == "unverified"
    assert fm["flash"] == {"method": "release-bin"}                                   # a binary exists; bin_url is a human promotion
    assert "bin_url" not in text
    assert [s["field"] for s in fm["sources"]] == ["*", "board", "board"]
    assert fm["sources"][0]["url"] == FW_URL and fm["sources"][1]["url"] == RELEASE_PAGE   # the page that lists the asset
    assert fm["sources"][2]["url"] == SIG_CI["url"]
    assert not any(s["url"].endswith(".bin") for s in fm["sources"])
    assert all(s["verified"] == TODAY for s in fm["sources"])
    assert "m5cardputer" in fm["notes"] and "asset esp32_marauder_v1_15_1_20260824_m5cardputer.bin" in fm["notes"]
    assert "release v1.15.1" in fm["notes"] and "not verified on hardware" in fm["notes"]
    assert "- rank 1 asset: `m5cardputer` — " + SIG_ASSET["url"] in text                 # the download URL stays in the prose for the human
    assert "- rank 3 ci: `m5stack-cardputer`" in text


def test_render_recipe_a_gz_asset_is_not_a_flashable_binary(tmp_path):
    gz = dict(SIG_ASSET, url=SIG_ASSET["url"] + ".gz", extra={"asset": "x.bin.gz", "release": "v1.15.1"})
    text = writers.render_recipe("m5cardputer__marauder", "m5cardputer", "marauder", "esp32-s3", FW_URL, [gz], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    assert "flash" not in _validate(tmp_path / "recipe.md", SOC.get)


def test_render_recipe_platformio_signal_yields_the_env_cited_under_flash_env(tmp_path):
    text = writers.render_recipe("esp32-s3-devkitc-1__wled", "esp32-s3-devkitc-1", "wled", "esp32-s3", "https://github.com/wled/WLED", [SIG_PIO], TODAY)
    (tmp_path / "recipe.md").write_text(text)
    fm = _validate(tmp_path / "recipe.md", SOC.get)
    assert fm["flash"] == {"env": "esp32s3dev_8MB_opi"}
    assert "(env esp32s3dev_8MB_opi)" in fm["notes"]
    assert [s["field"] for s in fm["sources"]] == ["*", "flash.env", "board"]
    assert fm["sources"][1]["url"] == SIG_PIO["url"] == fm["sources"][2]["url"]


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


def test_write_recipes_reads_board_socs_from_root_by_default(tmp_path):
    (tmp_path / "data" / "boards" / "acme" / "acme-one").mkdir(parents=True)
    (tmp_path / "data" / "boards" / "acme" / "acme-one" / "board.md").write_text("---\nid: acme-one\nsoc: esp32-c3\n---\n")
    res = writers.write_recipes("fw", "https://github.com/o/fw", {"boards": {"acme-one": [SIG_CI], "m5cardputer": [SIG_CI]}, "socs": {}},
                                root=tmp_path, today=TODAY)
    assert res["written"] == ["acme-one__fw"]                                        # m5cardputer exists in the real clone, not in root
    assert res["refused"] == [("m5cardputer", "board has no catalogued soc")]
    assert writers.socs_for("fw", tmp_path) == ["esp32-c3"]


def test_socs_for_reads_existing_recipes(tmp_path):
    for b in ("m5cardputer", "lolin-d32"):
        (tmp_path / "data" / "recipes" / f"{b}__fw").mkdir(parents=True)
        (tmp_path / "data" / "recipes" / f"{b}__fw" / "recipe.md").write_text("---\n---\n")
    (tmp_path / "data" / "recipes" / "m5cardputer__other").mkdir(parents=True)
    assert writers.socs_for("fw", tmp_path, board_soc=SOC.get) == ["esp32", "esp32-s3"]


# --- merge_socs -----------------------------------------------------------------------------------

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


def _fm(p: Path) -> dict:
    return yaml.safe_load(p.read_text().split("\n---\n")[0].split("---\n", 1)[1])


def test_merge_socs_widens_never_narrows_and_cites_every_proving_page(tmp_path):
    p = tmp_path / "firmware.md"
    p.write_text(FW_MD)
    urls = [RELEASE_PAGE, "https://github.com/justcallmekoko/ESP32Marauder/blob/master/sdkconfig.esp32c6"]
    assert writers.merge_socs(p, ["esp32-s3", "esp32", "esp32-c6"], urls, TODAY)
    fm = _fm(p)
    assert fm["socs"] == ["esp32", "esp32-c6", "esp32-s3"]
    assert fm["sources"][-2:] == [{"field": "socs", "url": urls[0], "verified": TODAY},
                                  {"field": "socs", "url": urls[1], "verified": TODAY}]
    assert fm["sources"][0]["field"] == "*" and fm["name"] == "ESP32 Marauder" and fm["category"] == "pentest"
    assert p.read_text().endswith('Body with "quotes" and ç stays.\n')
    assert not writers.merge_socs(p, ["esp32"], "https://x", TODAY)                 # narrower: no change, no citation
    assert not writers.merge_socs(p, ["esp32-s3"], "https://x", TODAY)              # already there
    assert p.read_text().count("field: socs") == 2


def test_merge_socs_single_url_string_and_missing_block_and_missing_sources(tmp_path):
    q = tmp_path / "fw2.md"
    q.write_text(FW_MD.replace("socs:\n- esp32\n", ""))
    assert writers.merge_socs(q, ["esp32-s3"], RELEASE_PAGE, TODAY)
    fm = _fm(q)
    assert fm["socs"] == ["esp32-s3"] and fm["name"] == "ESP32 Marauder" and fm["sources"][-1]["url"] == RELEASE_PAGE
    r = tmp_path / "fw3.md"
    r.write_text("---\nid: x\nname: X\n---\nbody\n")
    assert writers.merge_socs(r, ["esp32"], RELEASE_PAGE, TODAY)
    assert _fm(r) == {"id": "x", "name": "X", "socs": ["esp32"], "sources": [{"field": "socs", "url": RELEASE_PAGE, "verified": TODAY}]}
    assert r.read_text().endswith("---\nbody\n")


def test_merge_socs_keeps_indented_blocks_and_inline_lists_with_comments(tmp_path):
    p = tmp_path / "indented.md"
    p.write_text(FW_MD.replace("socs:\n- esp32\n", "socs:\n  - esp32\n  - esp32-c3\n")
                      .replace("sources:\n- field: '*'\n  url: https://github.com/justcallmekoko/ESP32Marauder\n  verified: '2026-08-24'\n",
                               "sources:\n  - field: '*'\n    url: https://github.com/justcallmekoko/ESP32Marauder\n    verified: '2026-08-24'\n"))
    assert writers.merge_socs(p, ["esp32-s3"], RELEASE_PAGE, TODAY)
    fm = _fm(p)
    assert fm["socs"] == ["esp32", "esp32-c3", "esp32-s3"]
    assert fm["sources"] == [{"field": "*", "url": FW_URL, "verified": "2026-08-24"}, {"field": "socs", "url": RELEASE_PAGE, "verified": TODAY}]
    assert "  - esp32-s3\n" in p.read_text() and "  - field: socs\n    url: " in p.read_text()   # indentation preserved
    q = tmp_path / "inline.md"
    q.write_text(FW_MD.replace("socs:\n- esp32\n", "socs: [esp32, esp32-c3]  # from the readme\n"))
    assert writers.merge_socs(q, ["esp32-s3"], RELEASE_PAGE, TODAY)
    assert _fm(q)["socs"] == ["esp32", "esp32-c3", "esp32-s3"]


@pytest.mark.parametrize("variant", [
    "socs: [esp32,\n  esp32-c3]\n",            # multi-line flow list
    "socs: esp32\n",                            # scalar
    "socs:\n- esp32\n- 7\n",                    # not all strings
])
def test_merge_socs_refuses_forms_it_cannot_rewrite_safely_and_leaves_the_file_alone(tmp_path, variant):
    p = tmp_path / "odd.md"
    text = FW_MD.replace("socs:\n- esp32\n", variant)
    p.write_text(text)
    with pytest.raises(ValueError):
        writers.merge_socs(p, ["esp32-s3"], RELEASE_PAGE, TODAY)
    assert p.read_text() == text


def test_merge_socs_refuses_crlf_and_no_fence_and_an_empty_source_list(tmp_path):
    p = tmp_path / "crlf.md"
    p.write_text(FW_MD.replace("\n", "\r\n"))
    with pytest.raises(ValueError):
        writers.merge_socs(p, ["esp32-s3"], RELEASE_PAGE, TODAY)
    q = tmp_path / "nofence.md"
    q.write_text("id: x\n")
    with pytest.raises(ValueError):
        writers.merge_socs(q, ["esp32-s3"], RELEASE_PAGE, TODAY)
    r = tmp_path / "nourl.md"
    r.write_text(FW_MD)
    with pytest.raises(ValueError):
        writers.merge_socs(r, ["esp32-s3"], [], TODAY)                                 # cite-or-omit
    assert r.read_text() == FW_MD


def test_merge_socs_verifies_its_rewrite_before_writing(tmp_path, monkeypatch):
    """A rewrite whose re-parse disagrees with the intent is refused, and nothing is written."""
    p = tmp_path / "fw.md"
    p.write_text(FW_MD)
    real = writers._block_span
    monkeypatch.setattr(writers, "_block_span", lambda lines, i: (i + 1, ""))        # a broken scanner: leaves the old items dangling
    with pytest.raises(ValueError, match="verification failed"):
        writers.merge_socs(p, ["esp32-s3"], RELEASE_PAGE, TODAY)
    assert p.read_text() == FW_MD
    monkeypatch.setattr(writers, "_block_span", real)
    assert writers.merge_socs(p, ["esp32-s3"], RELEASE_PAGE, TODAY)
