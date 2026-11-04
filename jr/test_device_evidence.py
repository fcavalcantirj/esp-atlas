"""Tests for jr/device_evidence.py — the device-build evidence gate (review finding 3, Warble).

Every repo shape is a fake (api, raw) pair: no live network."""
from __future__ import annotations

import pytest

import device_evidence as dev
import memory
from budget import BudgetExceeded


def fake_repo(owner_repo="o/r", ref="main", tree=None, files=None, releases=None, fail=()):
    """(api, raw, log) serving one repo: `tree` paths, `files` {path: text} on raw, `releases` the
    `releases?per_page=10` list. Anything else is a 404. `fail` paths raise a non-404 error."""
    files, log = files or {}, []

    def api(path):
        log.append(("api", path))
        if path in fail:
            raise RuntimeError("HTTP 502: bad gateway")
        if path == f"repos/{owner_repo}/git/trees/{ref}?recursive=1" and tree is not None:
            return {"tree": [{"path": p, "type": "blob"} for p in tree], "truncated": False}
        if path == f"repos/{owner_repo}/releases?per_page=10" and releases is not None:
            return releases
        raise RuntimeError("HTTP 404: Not Found")

    def raw(url):
        log.append(("raw", url))
        prefix = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/"
        if url in fail:
            raise RuntimeError("HTTP 503")
        return files.get(url[len(prefix):]) if url.startswith(prefix) else None

    return api, raw, log


WARBLE_TREE = ["go.mod", "go.sum", "cmd/warble/main.go", "internal/ws/server.go", "README.md",
               "Makefile", "docker-compose.yml"]

IDF_CMAKE = ("cmake_minimum_required(VERSION 3.16)\n"
             "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(blink)\n")


def test_warble_shaped_go_repo_has_no_device_build_signal():
    api, raw, _ = fake_repo("rebelthor/warble", tree=WARBLE_TREE, releases=[])
    res = dev.check("rebelthor/warble", api=api, raw=raw, ref="main")
    assert res["ok"] is False and res["kind"] is None
    assert dev.reject_reason(res).startswith("not_device_firmware:")


def test_platformio_espressif32_repo_passes_and_cites_the_platform_line():
    ini = "[env]\nframework = arduino\n\n[env:m5]\nplatform = espressif32@6.4.0\nboard = m5stack-cores3\n"
    api, raw, _ = fake_repo(tree=["platformio.ini", "src/main.cpp"], files={"platformio.ini": ini})
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "platformio"
    assert res["url"] == "https://github.com/o/r/blob/main/platformio.ini#L5"


def test_platformio_pioarduino_platform_url_and_interpolation_count_as_espressif32():
    ini = "[common]\nplatform = https://github.com/pioarduino/platform-espressif32/releases/download/55.03.30/platform-espressif32.zip\n" \
          "[env:x]\nplatform = ${common.platform}\nboard = esp32dev\n"
    api, raw, _ = fake_repo(tree=["firmware/platformio.ini"], files={"firmware/platformio.ini": ini})
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "platformio"
    assert res["url"].startswith("https://github.com/o/r/blob/main/firmware/platformio.ini#L")


def test_platformio_for_a_non_espressif_platform_is_not_evidence():
    ini = "[env:pico]\nplatform = raspberrypi\nboard = pico\n"
    api, raw, _ = fake_repo(tree=["platformio.ini", "src/main.cpp"], files={"platformio.ini": ini}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is False


def test_esp_idf_project_cmake_passes():
    api, raw, _ = fake_repo(tree=["CMakeLists.txt", "main/CMakeLists.txt", "main/app.c"],
                            files={"CMakeLists.txt": IDF_CMAKE, "main/CMakeLists.txt": "idf_component_register(SRCS app.c)\n"})
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "idf_project"
    assert res["url"] == "https://github.com/o/r/blob/main/CMakeLists.txt#L2"


def test_a_plain_cmake_project_is_not_evidence():
    api, raw, _ = fake_repo(tree=["CMakeLists.txt", "src/main.cpp"],
                            files={"CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\nproject(server CXX)\n"},
                            releases=[])
    assert dev.check("o/r", api=api, raw=raw, ref="main")["ok"] is False


def test_idf_component_manifest_passes_without_reading_it():
    api, raw, log = fake_repo(tree=["main/idf_component.yml", "main/app.c"])
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "idf_component"
    assert res["url"] == "https://github.com/o/r/blob/main/main/idf_component.yml"
    assert res["calls"] == 1 and [k for k, _ in log] == ["api"]       # the tree alone proves it


def test_arduino_sketch_passes_from_the_tree_alone():
    api, raw, log = fake_repo(tree=["README.md", "Sketch/Sketch.ino"])
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "arduino_sketch"
    assert res["url"] == "https://github.com/o/r/blob/main/Sketch/Sketch.ino"
    assert res["calls"] == 1


def test_release_bin_only_repo_passes():
    rels = [{"tag_name": "v2", "draft": False, "assets": [{"name": "notes.txt"}]},
            {"tag_name": "v1", "draft": False, "assets": [{"name": "fw-cardputer.bin",
                                                         "browser_download_url": "https://github.com/o/r/releases/download/v1/fw-cardputer.bin"}]}]
    api, raw, _ = fake_repo(tree=["README.md", "LICENSE"], releases=rels)
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "release_bin"
    assert res["url"] == "https://github.com/o/r/releases/download/v1/fw-cardputer.bin"


def test_a_draft_release_bin_is_not_evidence():
    rels = [{"tag_name": "v1", "draft": True, "assets": [{"name": "fw.bin", "browser_download_url": "u"}]}]
    api, raw, _ = fake_repo(tree=["README.md"], releases=rels)
    assert dev.check("o/r", api=api, raw=raw, ref="main")["ok"] is False


def test_unreadable_endpoints_are_unknown_never_a_rejection():
    """A 502 on the tree and the releases is not a fact about the repo: ok=None, retried soon."""
    api, raw, _ = fake_repo(tree=["x.ino"], releases=[],
                            fail=("repos/o/r/git/trees/main?recursive=1", "repos/o/r/releases?per_page=10"))
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is None
    reason = dev.reject_reason(res)
    assert reason.startswith("device_evidence_unreadable:")
    assert dev.ttl_days(reason) == memory.UNRESOLVED_REJECT_DAYS


def test_not_device_firmware_uses_the_no_build_signal_ttl():
    assert dev.ttl_days("not_device_firmware: whatever") == memory.NO_BUILD_SIGNAL_DAYS


def test_no_tree_listing_still_reads_root_build_files_and_releases():
    """A tree 404 (empty default branch listing) falls back to the root platformio.ini/CMakeLists."""
    api, raw, _ = fake_repo(files={"CMakeLists.txt": IDF_CMAKE}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, ref="main")
    assert res["ok"] is True and res["kind"] == "idf_project"


def test_call_cap_is_respected():
    many = [f"p{i}/platformio.ini" for i in range(10)]
    api, raw, log = fake_repo(tree=many, files={p: "[env:x]\nplatform = atmelavr\n" for p in many}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, ref="main", max_calls=4)
    assert res["calls"] <= 4 and len(log) <= 4


def test_budget_exceeded_propagates():
    def api(path):
        raise BudgetExceeded("tick budget")
    with pytest.raises(BudgetExceeded):
        dev.check("o/r", api=api, raw=lambda u: None, ref="main")


def test_ref_defaults_to_head():
    api, raw, log = fake_repo(ref="HEAD", tree=["a.ino"])
    assert dev.check("o/r", api=api, raw=raw)["ok"] is True
    assert log[0] == ("api", "repos/o/r/git/trees/HEAD?recursive=1")
