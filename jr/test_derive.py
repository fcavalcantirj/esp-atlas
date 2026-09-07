"""Tests for jr/derive.py — build-signal extraction on REAL fixtures, offline.

Fixtures under jr/fixtures/derive/ are verbatim copies of upstream files fetched 2026-09-07:
WLED platformio.ini (27 env/board pairs), Bruce platformio.ini + two boards/*.ini (extra_configs),
Marauder v1.15.1 release asset names, Meshtastic v2.7.26 release manifest (trimmed). `api` and
`raw` are fakes serving those files; nothing here touches the network or writes the tree.

Run: cd jr && python3 -m pytest test_derive.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import board_alias
import derive

FIX = Path(__file__).resolve().parent / "fixtures" / "derive"
WLED = (FIX / "wled-platformio.ini").read_text()
BRUCE = (FIX / "bruce-platformio.ini").read_text()
BRUCE_CYD = (FIX / "bruce-boards-CYD-2432S028.ini").read_text()
BRUCE_C5 = (FIX / "bruce-boards-ESP32-C5.ini").read_text()
MARAUDER_RELEASE = json.loads((FIX / "marauder-release.json").read_text())
MESHTASTIC_MANIFEST = json.loads((FIX / "meshtastic-manifest.json").read_text())


class Fake:
    """api(path) / raw(url) backed by dicts; records every call."""

    def __init__(self, api=None, raw=None):
        self._api, self._raw, self.calls = api or {}, raw or {}, []

    def api(self, path):
        self.calls.append(("api", path))
        if path not in self._api:
            raise RuntimeError("404")
        return self._api[path]

    def raw(self, url):
        self.calls.append(("raw", url))
        return self._raw.get(url)


def tree(paths):
    return {"tree": [{"path": p, "type": "blob"} for p in paths], "truncated": False}


# --- rank 2: platformio ---------------------------------------------------------------------------

def test_parse_platformio_wled_matches_the_regex_ground_truth():
    """27 envs declare `board =` themselves; the other 16 (esp32dev_debug, esp32dev_hub75, …)
    inherit it through `extends`, which is exactly how PlatformIO builds them. Same 18 boards."""
    p = derive.parse_platformio(WLED)
    with_board = {k: v for k, v in p["envs"].items() if v["board"]}
    assert len(p["envs"]) == 43 and len(with_board) == 43
    assert len({v["board"] for v in with_board.values()}) == 18
    assert with_board["esp32dev"]["board"] == "esp32dev" and with_board["esp32dev_debug"]["board"] == "esp32dev"
    assert with_board["esp32dev_debug"]["line"] == with_board["esp32dev"]["line"]        # cites the inherited line
    assert sorted({v["board"] for v in with_board.values()})[:3] == ["adafruit_matrixportal_esp32s3_wled", "esp01_1m", "esp32-c3-devkitm-1"]
    assert all(v["line"] > 0 for v in with_board.values())


def test_parse_platformio_reads_extra_configs_and_default_envs_including_continuation_lines():
    p = derive.parse_platformio(BRUCE)
    assert p["extra_configs"] == ["boards/*.ini", "boards/*/*.ini"]
    assert p["envs"] == {}                                        # Bruce keeps every env in boards/
    p2 = derive.parse_platformio("[platformio]\ndefault_envs = a, b\n  c\n[env:a]\nboard = x\n[env:native]\nplatform = native\n")
    assert p2["default_envs"] == ["a", "b", "c"] and p2["envs"]["a"]["board"] == "x" and p2["envs"]["native"]["board"] is None


def test_parse_platformio_resolves_board_through_extends_and_the_env_default():
    ini = ("[env]\nboard = default-board ; global\n\n[base]\nboard = base-board\n\n[mid]\nextends = base\n\n"
           "[env:leaf]\nextends = other, mid\n\n[env:own]\nextends = base\nboard = own-board\n\n[env:plain]\nplatform = espressif32\n")
    p = derive.parse_platformio(ini)
    assert p["envs"]["leaf"] == {"board": "base-board", "line": 5}
    assert p["envs"]["own"] == {"board": "own-board", "line": 15}
    assert p["envs"]["plain"] == {"board": "default-board", "line": 2}
    cyd = derive.parse_platformio(BRUCE_CYD)
    assert len(cyd["envs"]) == 13 and all(v["board"] == "CYD-2432S028" for v in cyd["envs"].values()), cyd["envs"]


def test_platformio_signals_expand_extra_configs_through_the_tree_and_skip_native():
    f = Fake(raw={
        "https://raw.githubusercontent.com/BruceDevices/firmware/main/platformio.ini": BRUCE,
        "https://raw.githubusercontent.com/BruceDevices/firmware/main/boards/CYD-2432S028/CYD-2432S028.ini": BRUCE_CYD,
        "https://raw.githubusercontent.com/BruceDevices/firmware/main/boards/ESP32-C5/ESP32-C5.ini": BRUCE_C5,
    })
    calls = derive._Calls(f.api, f.raw, 60)
    notes = []
    sigs = derive.platformio_signals("BruceDevices/firmware", "main", calls, notes,
                                     tree=["platformio.ini", "boards/CYD-2432S028/CYD-2432S028.ini", "boards/ESP32-C5/ESP32-C5.ini", "src/main.cpp"])
    assert notes == []
    boards = sorted({s.token for s in sigs})
    assert "esp32-c5-devkitc-1" in boards and "CYD-2432S028" in boards
    assert all(s.rank == 2 and s.kind == "platformio" and s.url.startswith("https://github.com/BruceDevices/firmware/blob/main/boards/") for s in sigs)
    assert all(s.extra["env"] != "native" for s in sigs)
    assert len(sigs) >= 13                                        # the CYD file alone declares 13 envs


def test_extra_configs_are_capped_and_the_cap_is_noted():
    paths = [f"boards/b{i}/b{i}.ini" for i in range(50)]
    raw = {"https://raw.githubusercontent.com/o/r/main/platformio.ini": "[platformio]\nextra_configs = boards/*/*.ini\n"}
    raw.update({f"https://raw.githubusercontent.com/o/r/main/{p}": f"[env:e{i}]\nboard = b{i}\n" for i, p in enumerate(paths)})
    f = Fake(raw=raw)
    calls = derive._Calls(f.api, f.raw, 200)
    notes = []
    sigs = derive.platformio_signals("o/r", "main", calls, notes, tree=paths)
    assert len(sigs) == derive.MAX_EXTRA_CONFIG_FILES and any("capped" in n for n in notes)


# --- rank 1: releases ----------------------------------------------------------------------------------

def test_common_prefix_strips_the_version_stamp_marauder_puts_on_every_asset():
    stems = [derive._stem(a["name"]) for a in MARAUDER_RELEASE["assets"] if a["name"].endswith(".bin")]
    assert derive.common_prefix(stems) == "esp32_marauder_v1_15_1_20260824_"
    assert derive.common_prefix(["only-one"]) == ""


def test_release_signals_yield_short_board_tokens_and_cite_the_asset():
    f = Fake(api={"repos/justcallmekoko/ESP32Marauder/releases/latest": MARAUDER_RELEASE})
    calls = derive._Calls(f.api, f.raw, 60)
    sigs = derive.release_signals("justcallmekoko/ESP32Marauder", calls, [])
    tokens = {s.token for s in sigs}
    assert {"m5cardputer", "m5stickc_plus2", "m5nanoc6", "esp32c5devkitc1", "t_dongle_c5", "flipper"} <= tokens
    assert "marauder-installer-assets" not in tokens                # a .zip is not a board bin
    s = next(s for s in sigs if s.token == "m5cardputer")
    assert s.rank == 1 and s.kind == "asset" and s.url.endswith("/esp32_marauder_v1_15_1_20260824_m5cardputer.bin")
    assert s.extra["release"] == "v1.15.1"
    assert f.calls == [("api", "repos/justcallmekoko/ESP32Marauder/releases/latest")]   # never an asset body


def test_manifest_signals_keep_only_esp32_platforms_with_their_chip():
    url = "https://github.com/meshtastic/firmware/releases/download/v2.7.26/firmware-2.7.26.json"
    sigs = derive.manifest_signals(MESHTASTIC_MANIFEST, url, "v2.7.26.54e0d8d")
    tokens = {s.token for s in sigs}
    assert "m5stack-cardputer-adv" in tokens and "t-watch-s3" in tokens
    assert not any(t in tokens for t in ("rak3172", "pico2", "feather_diy"))     # stm32 / rp2350 / nrf52
    s = next(s for s in sigs if s.token == "t-watch-s3")
    assert s.soc == "esp32-s3" and s.rank == 1 and s.kind == "manifest" and s.url == url


def test_esp_web_tools_manifest_shape_is_read_too():
    doc = {"name": "x", "builds": [{"chipFamily": "ESP32-S3", "parts": [{"path": "firmware-tbeam-s3-2.5.bin", "offset": 0}]},
                                   {"chipFamily": "ESP32-C3", "parts": [{"path": "sub/dir/xiao-c3.bin", "offset": 0}]}]}
    sigs = derive.manifest_signals(doc, "https://x/manifest.json", None)
    assert [(s.token, s.soc) for s in sigs] == [("firmware-tbeam-s3-2.5", "esp32-s3"), ("xiao-c3", "esp32-c3")]


def test_release_signals_read_a_small_manifest_asset_but_skip_big_ones():
    small = {"name": "firmware-1.json", "size": 900, "browser_download_url": "https://dl/firmware-1.json"}
    big = {"name": "firmware-big.json", "size": 10 * 1024 * 1024, "browser_download_url": "https://dl/big.json"}
    f = Fake(api={"repos/o/r/releases/latest": {"tag_name": "v1", "assets": [small, big]}},
             raw={"https://dl/firmware-1.json": json.dumps(MESHTASTIC_MANIFEST)})
    calls = derive._Calls(f.api, f.raw, 60)
    sigs = derive.release_signals("o/r", calls, [])
    assert any(s.kind == "manifest" for s in sigs)
    assert ("raw", "https://dl/big.json") not in f.calls


# --- rank 3 + 4 -----------------------------------------------------------------------------------------

def test_ci_signals_collect_matrix_scalars_including_include_entries():
    wf = "jobs:\n  build:\n    strategy:\n      matrix:\n        board: [m5stack-cardputer, esp32-s3-devkitc-1]\n        include:\n          - board: lilygo-t-deck\n            env: tdeck\n    steps: []\n"
    f = Fake(raw={"https://raw.githubusercontent.com/o/r/main/.github/workflows/build.yml": wf})
    calls = derive._Calls(f.api, f.raw, 60)
    sigs = derive.ci_signals("o/r", "main", calls, [], tree=[".github/workflows/build.yml", "README.md"])
    assert {s.token for s in sigs} == {"m5stack-cardputer", "esp32-s3-devkitc-1", "lilygo-t-deck", "tdeck"}
    assert all(s.rank == 3 and s.extra["workflow"] == ".github/workflows/build.yml" for s in sigs)


def test_idf_signals_read_component_targets_sdkconfig_and_in_repo_boards_txt():
    f = Fake(raw={
        "https://raw.githubusercontent.com/o/r/main/idf_component.yml": "targets:\n  - esp32s3\n  - esp32c6\n",
        "https://raw.githubusercontent.com/o/r/main/sdkconfig.defaults": 'CONFIG_IDF_TARGET="esp32s3"\nCONFIG_FOO=y\n',
        "https://raw.githubusercontent.com/o/r/main/boards.txt": "mine.name=My Board\nmine.build.mcu=esp32\n",
    })
    calls = derive._Calls(f.api, f.raw, 60)
    sigs = derive.idf_signals("o/r", "main", calls, [], tree=["idf_component.yml", "sdkconfig.defaults", "boards.txt"])
    assert {(s.kind, s.token, s.soc) for s in sigs} == {("idf", "esp32s3", "esp32-s3"), ("idf", "esp32c6", "esp32-c6"),
                                                        ("idf", "esp32s3", "esp32-s3"), ("boards_txt", "mine", None)}


# --- driver + budget ----------------------------------------------------------------------------------

def test_derive_walks_every_rank_counts_calls_and_never_raises_on_missing_signals():
    f = Fake(api={"repos/o/r": {"default_branch": "dev"}, "repos/o/r/git/trees/dev?recursive=1": tree(["README.md"])})
    d = derive.derive("o/r", api=f.api, raw=f.raw, today="2026-09-07")
    assert d == {"repo": "o/r", "ref": "dev", "fetched": "2026-09-07", "calls": 4, "signals": [], "notes": []}   # meta, tree, release, platformio.ini
    assert ("api", "repos/o/r/releases/latest") in f.calls and ("raw", "https://raw.githubusercontent.com/o/r/dev/platformio.ini") in f.calls


def test_derive_budget_cap_is_reported_not_raised():
    f = Fake(api={"repos/o/r": {"default_branch": "main"}})
    d = derive.derive("o/r", api=f.api, raw=f.raw, max_calls=1, today="2026-09-07")
    assert d["calls"] == 1 and any("budget exhausted" in n for n in d["notes"]) and d["signals"] == []


# --- resolve against the real catalog -----------------------------------------------------------------

@pytest.fixture(scope="module")
def real_catalog():
    board_alias.clear_caches()
    return board_alias.atlas_boards()


def test_resolve_maps_wled_and_marauder_signals_to_catalogued_boards_and_refuses_esp8266(real_catalog):
    f = Fake(api={"repos/justcallmekoko/ESP32Marauder/releases/latest": MARAUDER_RELEASE},
             raw={"https://raw.githubusercontent.com/wled/WLED/main/platformio.ini": WLED})
    calls = derive._Calls(f.api, f.raw, 60)
    sigs = derive.release_signals("justcallmekoko/ESP32Marauder", calls, [])
    sigs += derive.platformio_signals("wled/WLED", "main", calls, [], tree=["platformio.ini"])
    res = derive.resolve({"signals": [derive.asdict(s) for s in sigs]})
    boards = res["boards"]
    assert {"m5cardputer", "m5stick-cplus2", "m5nanoc6", "esp32-s3-devkitc-1", "lolin-s3-mini", "lolin-s2-mini", "esp32-c6-devkitc-1"} <= set(boards)
    assert boards["m5cardputer"][0]["rank"] == 1 and boards["m5cardputer"][0]["kind"] == "asset"
    assert boards["esp32-s3-devkitc-1"][0]["rank"] == 2 and boards["esp32-s3-devkitc-1"][0]["extra"]["env"]
    unresolved_tokens = {s["token"] for s in res["unresolved"]}
    assert {"nodemcuv2", "esp01_1m", "esp_wroom_02"} <= unresolved_tokens          # ESP8266: never a board here
    assert not any(b["soc"] == "esp32" and "s3" in tok for tok, b in ((s["token"], real_catalog.get(k, {})) for k, sigs_ in boards.items() for s in sigs_))


def test_resolve_puts_chip_only_signals_under_socs():
    res = derive.resolve({"signals": [{"rank": 4, "kind": "idf", "token": "esp32s3", "soc": "esp32-s3", "url": "u", "line": 1, "extra": {}},
                                      {"rank": 1, "kind": "asset", "token": "not-a-board-at-all-xyz", "soc": None, "url": "u", "line": None, "extra": {}}]})
    assert list(res["socs"]) == ["esp32-s3"] and res["boards"] == {} and [s["token"] for s in res["unresolved"]] == ["not-a-board-at-all-xyz"]
