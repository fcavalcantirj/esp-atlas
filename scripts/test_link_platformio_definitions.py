"""scripts/link_platformio_definitions.py — boards link to PlatformIO definitions only by evidence. No network."""
import yaml

import link_platformio_definitions as lp

D = "a" * 64


def man(url, mcu="esp32s3", lineages=("official", "pioarduino")):
    return {lin: {"url": url, "mcu": mcu, "digest": (D if lin == "official" else "b" * 64)} for lin in lineages}


def test_r1_a_board_that_cites_the_manifest_file_links_every_cited_definition():
    boards = {"esp32-s3-devkitc-1": {"soc": "esp32-s3", "urls": [
        "https://github.com/pioarduino/platform-espressif32/blob/32f6bf4/boards/esp32-s3-devkitc-1.json",
        "https://github.com/pioarduino/platform-espressif32/blob/32f6bf4/boards/esp32-s3-devkitc1-n16r8.json"]}}
    manifests = {"esp32-s3-devkitc-1": man("https://docs.espressif.com/x"), "esp32-s3-devkitc1-n16r8": man("https://docs.espressif.com/y")}
    links, refusals = lp.plan(boards, manifests)
    assert links == {"esp32-s3-devkitc-1": ["esp32-s3-devkitc-1", "esp32-s3-devkitc1-n16r8"]} and refusals == []


def test_r2_the_manifest_product_url_among_the_cited_sources_links_one_definition():
    boards = {"heltec-wifi-kit-32-v3": {"soc": "esp32-s3", "urls": ["http://www.heltec.org/project/wifi-kit-32-v3"]}}
    links, _ = lp.plan(boards, {"heltec_wifi_kit_32_V3": man("https://heltec.org/project/wifi-kit-32-v3/")})
    assert links == {"heltec-wifi-kit-32-v3": ["heltec_wifi_kit_32_V3"]}


def test_r2_never_links_several_definitions_to_one_board():
    # XIAO: the shared Seeed page is the product url of both the S3 and the different S3 Plus definition
    boards = {"xiao-esp32s3": {"soc": "esp32-s3", "urls": ["https://wiki.seeedstudio.com/xiao"]}}
    manifests = {"seeed_xiao_esp32s3": man("https://wiki.seeedstudio.com/xiao"),
                 "seeed_xiao_esp32_s3_plus": man("https://wiki.seeedstudio.com/xiao")}
    links, refusals = lp.plan(boards, manifests)
    assert links == {} and "several definitions" in refusals[0][1]


def test_a_definition_never_links_to_two_boards():
    url = "https://www.adafruit.com/product/5700"
    boards = {"adafruit-qt-py-esp32-s3": {"soc": "esp32-s3", "urls": [url]},
              "adafruit-qt-py-esp32-s3-no-psram": {"soc": "esp32-s3", "urls": [url]}}
    links, refusals = lp.plan(boards, {"adafruit_qtpy_esp32s3_nopsram": man(url)})
    assert links == {} and len(refusals) == 2 and all("several boards" in r for _b, r in refusals)


def test_a_manifest_for_another_chip_is_refused():
    boards = {"some-c6-board": {"soc": "esp32-c6", "urls": ["https://vendor.example/p"]}}
    links, refusals = lp.plan(boards, {"some_board": man("https://vendor.example/p", mcu="esp32s3")})
    assert links == {} and "mcu" in refusals[0][1]


def test_one_entry_and_one_cited_manifest_per_lineage():
    entries, urls = lp.entries_for(["heltec_wifi_kit_32_V3"], {"heltec_wifi_kit_32_V3": man("u")})
    assert [e["platform_package"] for e in entries] == [lp.LINEAGES["official"][2], lp.LINEAGES["pioarduino"][2]]
    assert entries[0]["manifest_digest"] == D
    assert urls == ["https://github.com/platformio/platform-espressif32/blob/v8.0.0/boards/heltec_wifi_kit_32_V3.json",
                    "https://github.com/pioarduino/platform-espressif32/blob/61.04.00/boards/heltec_wifi_kit_32_V3.json"]


BOARD = """---
id: heltec-wifi-kit-32-v3
type: board
brand: heltec
name: WiFi Kit 32 V3
soc: esp32-s3
sources:
- field: '*'
  url: https://heltec.org/project/wifi-kit32-v3/
  verified: '2026-09-01'
---

Body text.
"""


def test_write_adds_only_the_definitions_and_their_sources(tmp_path):
    p = tmp_path / "board.md"
    p.write_text(BOARD, encoding="utf-8")
    entries, urls = lp.entries_for(["heltec_wifi_kit_32_V3"], {"heltec_wifi_kit_32_V3": man("u")})
    assert lp.write_definitions(p, entries, urls, "2026-11-22") is True
    text = p.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---")[1])
    assert fm["platformio_definitions"] == entries
    assert fm["sources"][0] == {"field": "*", "url": "https://heltec.org/project/wifi-kit32-v3/", "verified": "2026-09-01"}
    assert [s["url"] for s in fm["sources"][1:]] == urls and text.endswith("\nBody text.\n")
    assert lp.write_definitions(p, entries, urls, "2026-11-22") is False       # idempotent


def test_write_never_overwrites_different_definitions(tmp_path):
    p = tmp_path / "board.md"
    p.write_text(BOARD.replace("sources:", "platformio_definitions:\n- id: other\n  platform_package: x\n  manifest_digest: "
                               + "c" * 64 + "\nsources:"), encoding="utf-8")
    entries, urls = lp.entries_for(["heltec_wifi_kit_32_V3"], {"heltec_wifi_kit_32_V3": man("u")})
    before = p.read_text(encoding="utf-8")
    try:
        lp.write_definitions(p, entries, urls, "2026-11-22")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert p.read_text(encoding="utf-8") == before


def test_a_text_edit_that_would_change_anything_else_is_refused_and_writes_nothing(tmp_path, monkeypatch):
    """Verify-before-write: if the line edit lands wrong (forced here by misplacing the sources tail), the
    re-parse differs from the expected record, nothing is written and ValueError is raised."""
    p = tmp_path / "board.md"
    p.write_text(BOARD, encoding="utf-8")
    entries, urls = lp.entries_for(["heltec_wifi_kit_32_V3"], {"heltec_wifi_kit_32_V3": man("u")})
    real = lp._block_span
    monkeypatch.setattr(lp, "_block_span", lambda lines, i: (real(lines, i)[0] - 2, real(lines, i)[1]))
    before = p.read_text(encoding="utf-8")
    try:
        lp.write_definitions(p, entries, urls, "2026-11-22")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert p.read_text(encoding="utf-8") == before
