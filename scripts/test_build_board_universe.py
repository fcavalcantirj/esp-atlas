"""Tests for scripts/build_board_universe.py — offline, on tmp_path fixtures; no network.

Repo data read: data/socs/ (through esp_atlas_core.validate.known_ids) to pin the mcu → soc
mapping, and the committed data/board_universe.json, which one test gates (shape, citations,
ordering) since no catalog walker ever opens it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_board_universe as bbu  # noqa: E402

BOARDS_TXT = """\
# comment line
menu.PartitionScheme=Partition Scheme

esp32s3.name=ESP32S3 Dev Module
esp32s3.menu.PartitionScheme.default=Default 4MB
esp32s3.menu.PartitionScheme.custom.build.mcu=bogus-nested-mcu
esp32s3.menu.PSRAM.opi.build.variant=bogus-nested-variant
esp32s3.build.mcu=esp32s3
esp32s3.build.variant=esp32s3
esp32s3.build.board=ESP32S3_DEV

m5stack_cardputer.name=M5Cardputer
m5stack_cardputer.build.mcu=esp32s3
m5stack_cardputer.build.variant=m5stack_cardputer
m5stack_cardputer.build.board=M5STACK_CARDPUTER

nested.sub.name=Not A Board
esp32_family.name=ESP32 Family Device
esp32_family.build.board=ESP32_FAMILY

weird.name=Chip From The Future
weird.build.mcu=esp32zz
orphan.build.mcu=esp32s3
"""

PIO_STAMPS3 = {"name": "M5Stack StampS3", "vendor": "M5Stack", "url": "https://docs.m5stack.com/en/core/StampS3",
               "build": {"mcu": "esp32s3", "variant": "m5stack_stamp_s3"}}
PIO_C61 = {"name": "ESP32-C61 DevKitC-1", "vendor": "Espressif", "build": {"mcu": "esp32c61", "variant": "esp32c61"}}
PIO_NOBUILD = {"name": "Odd Board", "vendor": "Nobody"}
SOCS = {"esp32", "esp32-s3", "esp32-c61"}
SHA_A, SHA_B = "a" * 40, "b" * 40


@pytest.fixture
def fixtures(tmp_path):
    (tmp_path / "boards.txt").write_text(BOARDS_TXT, encoding="utf-8")
    (tmp_path / "pio").mkdir()
    (tmp_path / "pio" / "m5stack-stamps3.json").write_text(json.dumps(PIO_STAMPS3), encoding="utf-8")
    (tmp_path / "pio" / "esp32-c61-devkitc1.json").write_text(json.dumps(PIO_C61), encoding="utf-8")
    (tmp_path / "pio" / "odd.json").write_text(json.dumps(PIO_NOBUILD), encoding="utf-8")
    (tmp_path / "refs.json").write_text(json.dumps({"arduino_sha": SHA_A, "pio_sha": SHA_B}), encoding="utf-8")
    return tmp_path


# --- parser ------------------------------------------------------------------------------------

def test_parse_boards_txt_reads_only_strict_top_level_keys():
    boards = bbu.parse_boards_txt(BOARDS_TXT)
    assert set(boards) == {"esp32s3", "m5stack_cardputer", "esp32_family", "weird"}
    # nested keys (menu.*.build.mcu, x.y.name) never create a board nor override a field
    assert boards["esp32s3"] == {"name": "ESP32S3 Dev Module", "line": 4, "mcu": "esp32s3",
                                 "variant": "esp32s3", "board_define": "ESP32S3_DEV"}
    assert "nested" not in boards and "nested.sub" not in boards
    assert "orphan" not in boards                     # build.* with no .name is dropped
    assert boards["m5stack_cardputer"]["line"] == 12
    assert boards["esp32_family"] == {"name": "ESP32 Family Device", "line": 18, "board_define": "ESP32_FAMILY"}


def test_parse_boards_txt_counts_lines_on_newline_only_and_tolerates_crlf():
    crlf = BOARDS_TXT.replace("\n", "\r\n")
    assert bbu.parse_boards_txt(crlf)["m5stack_cardputer"]["line"] == 12
    with_ff = BOARDS_TXT.replace("# comment line", "# comment\x0cline")   # a form feed is not a line
    assert bbu.parse_boards_txt(with_ff)["m5stack_cardputer"]["line"] == 12


def test_soc_mapping_is_mechanical_but_gated_on_the_catalog():
    assert bbu.soc_for("esp32s3", SOCS) == "esp32-s3"
    assert bbu.soc_for("ESP32C61", SOCS) == "esp32-c61"
    assert bbu.soc_for("esp32c3", SOCS) is None          # mechanical map exists, soc not in this catalog
    assert bbu.soc_for("esp32zz", SOCS) is None          # unknown mcu
    assert bbu.soc_for(None, SOCS) is None


def test_soc_mapping_covers_every_mcu_the_real_catalog_knows():
    from esp_atlas_core.validate import known_ids
    real = known_ids()["soc"]
    for mcu, soc in bbu._MCU_TO_SOC.items():
        assert soc in real, f"{mcu} → {soc} is not a catalogued soc"


# --- assembly ----------------------------------------------------------------------------------

def test_build_universe_is_deterministic_cites_raw_plus_line_and_dates_only_the_sources(fixtures):
    inputs = bbu.gather_offline(fixtures)
    u1 = bbu.build_universe(today="2026-09-07", known_socs=SOCS, **inputs)
    u2 = bbu.build_universe(today="2026-09-07", known_socs=SOCS, **inputs)
    assert u1 == u2
    keys = [b["key"] for b in u1["boards"]]
    assert keys == sorted(keys) == ["arduino-esp32:esp32_family", "arduino-esp32:esp32s3",
                                    "arduino-esp32:m5stack_cardputer", "arduino-esp32:weird",
                                    "pioarduino:esp32-c61-devkitc1", "pioarduino:m5stack-stamps3", "pioarduino:odd"]
    card = next(b for b in u1["boards"] if b["key"] == "arduino-esp32:m5stack_cardputer")
    assert card["url"] == "https://raw.githubusercontent.com/espressif/arduino-esp32/" + SHA_A + "/boards.txt"
    assert card["line"] == 12 and card["soc"] == "esp32-s3" and card["board_define"] == "M5STACK_CARDPUTER"
    assert "verified" not in card and "generated" not in card       # dates live on sources[]
    stamp = next(b for b in u1["boards"] if b["key"] == "pioarduino:m5stack-stamps3")
    assert stamp["url"] == "https://github.com/pioarduino/platform-espressif32/blob/" + SHA_B + "/boards/m5stack-stamps3.json"
    assert stamp["vendor"] == "M5Stack" and stamp["vendor_url"].startswith("https://docs.m5stack.com/")
    assert stamp["variant"] == "m5stack_stamp_s3" and stamp["soc"] == "esp32-s3"
    odd = next(b for b in u1["boards"] if b["key"] == "pioarduino:odd")
    assert odd["mcu"] is None and odd["soc"] is None and odd["variant"] is None
    weird = next(b for b in u1["boards"] if b["id"] == "weird")
    assert weird["mcu"] == "esp32zz" and weird["soc"] is None
    assert all("atlas_id" not in b for b in u1["boards"])            # resolution is not the artifact's job
    assert "launcher_categories" not in u1                           # never a data source
    assert [s["count"] for s in u1["sources"]] == [4, 3]
    assert u1["sources"][0] == {"name": "arduino-esp32 boards.txt", "repo": "espressif/arduino-esp32", "ref": SHA_A,
                                "url": card["url"], "fetched": "2026-09-07", "count": 4}
    assert u1["sources"][1]["ref"] == SHA_B and u1["sources"][1]["fetched"] == "2026-09-07"


def test_a_refresh_with_unchanged_upstreams_rewrites_only_the_date_lines(fixtures):
    inputs = bbu.gather_offline(fixtures)
    a = json.dumps(bbu.build_universe(today="2026-09-07", known_socs=SOCS, **inputs), indent=1, sort_keys=True)
    b = json.dumps(bbu.build_universe(today="2026-10-07", known_socs=SOCS, **inputs), indent=1, sort_keys=True)
    changed = [x for x, y in zip(a.splitlines(), b.splitlines()) if x != y]
    assert len(changed) == 3 and all("2026-09-07" in x for x in changed)   # generated + 2 × fetched


def test_main_offline_writes_the_artifact_with_a_trailing_newline(fixtures, tmp_path, capsys):
    out = tmp_path / "u.json"
    rc = bbu.main(["--offline", "--fixtures", str(fixtures), "--out", str(out), "--today", "2026-09-07"])
    assert rc == 0
    raw = out.read_text(encoding="utf-8")
    assert raw.endswith("}\n")
    data = json.loads(raw)
    assert data["generated"] == "2026-09-07" and len(data["boards"]) == 7
    assert "wrote" in capsys.readouterr().out


def test_gather_live_pins_shas_walks_the_listing_and_sends_the_token_only_to_the_api(monkeypatch):
    calls, auth = [], []
    monkeypatch.setenv("GH_TOKEN", "t0k")

    def fetch(url, timeout=60.0):
        calls.append(url)
        if url.endswith("/commits/master"):
            return json.dumps({"sha": "c" * 40}).encode()
        if url.endswith("/commits/develop"):
            return json.dumps({"sha": "d" * 40}).encode()
        if "/boards.txt" in url:
            assert "c" * 40 in url
            return BOARDS_TXT.encode()
        if "/contents/boards?ref=" in url:
            return json.dumps([{"name": "m5stack-stamps3.json", "type": "file"}, {"name": "README.md", "type": "file"},
                               {"name": "extra.json", "type": "dir"}]).encode()
        if url.endswith("/boards/m5stack-stamps3.json"):
            assert "d" * 40 in url
            return json.dumps(PIO_STAMPS3).encode()
        raise AssertionError(url)
    inputs = bbu.gather_live(fetch=fetch, log=lambda *a: None)
    assert inputs["arduino_sha"] == "c" * 40 and inputs["pio_sha"] == "d" * 40
    assert list(inputs["pio_boards"]) == ["m5stack-stamps3"]
    assert not any(u.endswith("README.md") or "extra" in u for u in calls)

    # the real fetcher attaches GH_TOKEN only for api.github.com
    class Cap:
        def __init__(self, req, *a, **k):
            auth.append((req.full_url, req.get_header("Authorization")))
            raise OSError("no network in tests")
    monkeypatch.setattr(bbu.urllib.request, "urlopen", Cap)
    for url in ("https://api.github.com/repos/x/y/commits/master", "https://raw.githubusercontent.com/x/y/z/boards.txt"):
        with pytest.raises(OSError):
            bbu.default_fetch(url)
    assert auth == [("https://api.github.com/repos/x/y/commits/master", "Bearer t0k"),
                    ("https://raw.githubusercontent.com/x/y/z/boards.txt", None)]


# --- the committed artifact ----------------------------------------------------------------------

def test_committed_artifact_is_well_formed_cited_and_sorted():
    path = bbu.OUT_DEFAULT
    u = json.loads(path.read_text(encoding="utf-8"))
    assert set(u) == {"generated", "sources", "boards"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", u["generated"])
    assert [s["name"] for s in u["sources"]] == ["arduino-esp32 boards.txt", "pioarduino boards/*.json"]
    for s in u["sources"]:
        assert re.fullmatch(r"[0-9a-f]{40}", s["ref"]) and s["fetched"] == u["generated"] and s["count"] > 0
    keys = [b["key"] for b in u["boards"]]
    assert keys == sorted(keys) and len(keys) == len(set(keys))
    counts = {"arduino-esp32": 0, "pioarduino": 0}
    for b in u["boards"]:
        assert b["key"] == f"{b['source']}:{b['id']}" and b["name"]
        counts[b["source"]] += 1
        if b["source"] == "arduino-esp32":
            assert b["url"] == u["sources"][0]["url"] and isinstance(b["line"], int) and b["line"] > 0
        else:
            assert b["url"].startswith("https://github.com/pioarduino/platform-espressif32/blob/" + u["sources"][1]["ref"] + "/boards/")
        if b["mcu"] is not None:
            assert b["soc"] == bbu._MCU_TO_SOC.get(b["mcu"].lower()) or b["soc"] is None
        assert "verified" not in b and "atlas_id" not in b
    assert counts == {s["name"].split()[0]: s["count"] for s in u["sources"]} | {"arduino-esp32": u["sources"][0]["count"], "pioarduino": u["sources"][1]["count"]}
    assert len(u["boards"]) >= 600
