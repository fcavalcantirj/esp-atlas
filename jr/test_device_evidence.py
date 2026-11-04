"""Tests for jr/device_evidence.py — the device-build evidence gate (review finding 3, Warble).

Owner rule: admitted only with evidence the repo TARGETS an ESP chip, never a generic build file or
binary; an ambiguous repo goes to human review, never guessed. Every repo shape is a fake
(api, raw, head) triple: no live network."""
from __future__ import annotations

from pathlib import Path

import pytest

import device_evidence as dev
import memory
from budget import BudgetExceeded

REAL_DEFAULT_HEAD = dev.default_head      # bound at import: conftest replaces the module's with an offline stub


def fake_repo(owner_repo="o/r", ref="main", tree=None, files=None, releases=None, assets=None, fail=()):
    """(api, raw, head, log) serving one repo: `tree` paths, `files` {path: text} on raw, `releases`
    the `releases?per_page=10` list, `assets` {download url: bytes} for ranged GETs. Anything else
    is a 404. `fail` paths/urls raise a non-404 error."""
    files, assets, log = files or {}, assets or {}, []

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

    def head(url, nbytes):
        log.append(("head", url, nbytes))
        if url in fail:
            raise RuntimeError("HTTP 503")
        data = assets.get(url)
        return None if data is None else data[:nbytes]

    return api, raw, head, log


def check(owner_repo="o/r", **shape):
    api, raw, head, log = fake_repo(owner_repo, **shape)
    return dev.check(owner_repo, api=api, raw=raw, head=head, ref="main"), log


ESP_IMAGE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "esp_image"
# A whole ESP32-S3 app image written by the pinned esptool (jr/fixtures/esp_image/build.py).
VALID_S3_IMAGE = (ESP_IMAGE_FIXTURES / "app_esp32s3.bin").read_bytes()


def release(*names, draft=False):
    return [{"tag_name": "v1", "draft": draft,
             "assets": [{"name": n, "browser_download_url": f"https://github.com/o/r/releases/download/v1/{n}"}
                        for n in names]}]


def asset_url(name):
    return f"https://github.com/o/r/releases/download/v1/{name}"


WARBLE_TREE = ["go.mod", "go.sum", "cmd/warble/main.go", "internal/ws/server.go", "README.md",
               "Makefile", "docker-compose.yml"]

IDF_CMAKE = ("cmake_minimum_required(VERSION 3.16)\n"
             "include($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(blink)\n")
IDF_TREE = ["CMakeLists.txt", "main/CMakeLists.txt", "main/app.c"]
ESP_SKETCH_YAML = "default_fqbn: esp32:esp32:esp32s3\ndefault_port: /dev/ttyACM0\n"


# --- the owner's fixtures --------------------------------------------------------------------------

def test_warble_shaped_go_repo_is_not_device_firmware():
    res, _ = check("rebelthor/warble", tree=WARBLE_TREE, releases=[])
    assert res["ok"] is False and res["verdict"] == dev.NOT_DEVICE_FIRMWARE and res["kind"] is None
    assert dev.reject_reason(res).startswith("not_device_firmware:")


def test_platformio_espressif32_is_esp_target_and_cites_the_platform_line():
    ini = "[env]\nframework = arduino\n\n[env:m5]\nplatform = espressif32@6.4.0\nboard = m5stack-cores3\n"
    res, _ = check(tree=["platformio.ini", "src/main.cpp"], files={"platformio.ini": ini})
    assert res["ok"] is True and res["verdict"] == dev.ESP_TARGET and res["kind"] == "platformio"
    assert res["url"] == "https://github.com/o/r/blob/main/platformio.ini#L5"


def test_idf_project_with_sdkconfig_defaults_target_is_esp_target():
    res, _ = check(tree=IDF_TREE + ["sdkconfig.defaults"],
                   files={"CMakeLists.txt": IDF_CMAKE, "sdkconfig.defaults": "CONFIG_FREERTOS_HZ=1000\nCONFIG_IDF_TARGET=\"esp32s3\"\n"})
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "idf_project"
    assert res["url"] == "https://github.com/o/r/blob/main/sdkconfig.defaults#L2"
    assert any("esp32s3" in n for n in res["notes"])


def test_idf_project_cmake_without_a_stated_target_needs_review():
    res, _ = check(tree=IDF_TREE, files={"CMakeLists.txt": IDF_CMAKE}, releases=[])
    assert res["ok"] is False and res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "idf_project"
    assert res["url"] == "https://github.com/o/r/blob/main/CMakeLists.txt#L2"
    reason = dev.reject_reason(res)
    assert reason.startswith("needs_review_target:") and "project.cmake" in reason


def test_bare_ino_needs_review():
    res, _ = check(tree=["README.md", "Sketch/Sketch.ino"], releases=[])
    assert res["ok"] is False and res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "arduino_sketch"
    assert res["url"] == "https://github.com/o/r/blob/main/Sketch/Sketch.ino"


def test_ino_with_sketch_yaml_esp32_fqbn_is_esp_target():
    res, _ = check(tree=["Sketch/Sketch.ino", "Sketch/sketch.yaml"], files={"Sketch/sketch.yaml": ESP_SKETCH_YAML})
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "arduino_sketch"
    assert res["url"] == "https://github.com/o/r/blob/main/Sketch/sketch.yaml#L1"


def test_release_bin_with_a_valid_esp32s3_image_is_esp_target():
    res, log = check(tree=["README.md"], releases=release("fw-cardputer.bin"),
                     assets={asset_url("fw-cardputer.bin"): VALID_S3_IMAGE})
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "release_bin"
    assert res["url"] == asset_url("fw-cardputer.bin")
    assert any("esp32s3" in n and "checksum" in n and "SHA-256 verified" in n for n in res["notes"])
    assert [e for e in log if e[0] == "head"] == [("head", asset_url("fw-cardputer.bin"), dev.MAX_IMAGE_BYTES)]   # one GET, capped


def test_release_bin_without_the_esp_magic_needs_review():
    res, _ = check(tree=["README.md"], releases=release("fw.bin"), assets={asset_url("fw.bin"): b"\x7fELF" + bytes(12)})
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "release_bin"
    assert res["url"] == asset_url("fw.bin")


def test_uf2_only_release_needs_review_without_reading_it():
    res, log = check(tree=["README.md"], releases=release("fw.uf2"))
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "release_bin"
    assert not [e for e in log if e[0] == "head"]


# --- idf_project: where a target may be stated ------------------------------------------------------

def test_idf_component_yml_targets_state_the_target():
    comp = "dependencies:\n  idf: '>=5.1'\ntargets:\n  - esp32c6\n  - esp32h2\n"
    res, _ = check(tree=IDF_TREE + ["main/idf_component.yml"], files={"CMakeLists.txt": IDF_CMAKE, "main/idf_component.yml": comp})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/main/idf_component.yml#L4"


def test_idf_component_yml_flow_style_targets_count():
    res, _ = check(tree=IDF_TREE + ["main/idf_component.yml"],
                   files={"CMakeLists.txt": IDF_CMAKE, "main/idf_component.yml": "targets: [esp32, esp32s3]\n"})
    assert res["verdict"] == dev.ESP_TARGET


def test_dependencies_lock_target_states_the_target():
    lock = "dependencies:\n  idf:\n    version: 5.3.1\nmanifest_hash: abc\ntarget: esp32p4\nversion: 2.0.0\n"
    res, _ = check(tree=IDF_TREE + ["dependencies.lock"], files={"CMakeLists.txt": IDF_CMAKE, "dependencies.lock": lock})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/dependencies.lock#L5"


def test_a_non_esp_idf_target_is_not_a_stated_esp_target():
    res, _ = check(tree=IDF_TREE + ["sdkconfig.defaults"], releases=[],
                   files={"CMakeLists.txt": IDF_CMAKE, "sdkconfig.defaults": "CONFIG_IDF_TARGET=\"linux\"\n"})
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_a_target_stated_without_an_idf_project_is_not_evidence():
    """An idf_component.yml with no project.cmake is a component, not a firmware: owner review."""
    res, _ = check(tree=["idf_component.yml", "src/lib.c"], files={"idf_component.yml": "targets:\n  - esp32s3\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "idf_component"


def test_a_plain_cmake_project_is_not_device_firmware():
    res, _ = check(tree=["CMakeLists.txt", "src/main.cpp"], releases=[],
                   files={"CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\nproject(server CXX)\n"})
    assert res["verdict"] == dev.NOT_DEVICE_FIRMWARE


def test_no_tree_listing_still_reads_root_build_and_target_files():
    """A tree 404 falls back to the root CMakeLists.txt and the project's own target files."""
    res, _ = check(files={"CMakeLists.txt": IDF_CMAKE, "sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32c3\n"}, releases=[])
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "idf_project"


# --- arduino: where an ESP board may be named --------------------------------------------------------

def test_a_build_workflow_compiling_for_esp32_names_the_board():
    wf = "jobs:\n  build:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:m5stack_cardputer Sketch\n"
    res, _ = check(tree=["Sketch/Sketch.ino", ".github/workflows/build.yml"], files={".github/workflows/build.yml": wf})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/.github/workflows/build.yml#L4"


def test_library_properties_architectures_esp32_names_the_board():
    props = "name=Zap\nversion=1.0.0\narchitectures=avr, esp32\n"
    res, _ = check(tree=["examples/Zap/Zap.ino", "library.properties"], files={"library.properties": props})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/library.properties#L3"


def test_library_properties_any_architecture_does_not_name_an_esp():
    res, _ = check(tree=["examples/Zap/Zap.ino", "library.properties"], files={"library.properties": "architectures=*\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_a_non_esp_fqbn_does_not_name_an_esp():
    res, _ = check(tree=["S/S.ino", "S/sketch.yaml"], files={"S/sketch.yaml": "default_fqbn: arduino:avr:uno\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW


# --- release_bin: the whole image, validated offline (jr/esp_image.py) ---------------------------------

def test_a_bare_esp_image_header_is_no_longer_enough():
    """The old gate passed on 16 bytes (0xE9 + chip id 9). A header is not an image: review."""
    res, _ = check(tree=["README.md"], releases=release("fw.bin"), assets={asset_url("fw.bin"): VALID_S3_IMAGE[:16]})
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "release_bin"
    assert "truncated" in dev.review_note(res)["why"]


@pytest.mark.parametrize("fixture,why", [("bad_checksum.bin", "checksum mismatch"), ("bad_sha256.bin", "SHA-256 mismatch"),
                                         ("corrupt_after_first_segment.bin", "checksum mismatch"),
                                         ("merged_bootloader_0x0.bin", "merged flash image"),
                                         ("merged_bootloader_0x1000.bin", "merged flash image"),
                                         ("unknown_chip.bin", "unknown chip id"), ("truncated.bin", "truncated")])
def test_a_release_bin_failing_validation_needs_review_with_the_validator_s_reason(fixture, why):
    data = (ESP_IMAGE_FIXTURES / fixture).read_bytes()
    res, _ = check(tree=["README.md"], releases=release("fw.bin"), assets={asset_url("fw.bin"): data})
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "release_bin" and res["url"] == asset_url("fw.bin")
    assert why in dev.review_note(res)["why"] and why in dev.reject_reason(res)


def test_a_release_bin_asset_that_404s_needs_review():
    res, _ = check(tree=["README.md"], releases=release("fw.bin"), assets={})
    assert res["verdict"] == dev.NEEDS_REVIEW and "not readable" in dev.review_note(res)["why"]


def test_the_probe_prefers_the_app_image_over_a_partition_table():
    res, log = check(tree=["README.md"], releases=release("partitions.bin", "app.bin"),
                     assets={asset_url("partitions.bin"): b"\xaa\x50" + bytes(14), asset_url("app.bin"): VALID_S3_IMAGE})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == asset_url("app.bin")
    assert [e[1] for e in log if e[0] == "head"] == [asset_url("app.bin")]


def test_a_draft_release_bin_is_not_evidence():
    res, log = check(tree=["README.md"], releases=release("fw.bin", draft=True), assets={asset_url("fw.bin"): VALID_S3_IMAGE})
    assert res["verdict"] == dev.NOT_DEVICE_FIRMWARE and not [e for e in log if e[0] == "head"]


def test_default_head_sends_one_ranged_get_and_reads_only_the_header(monkeypatch):
    import urllib.request
    seen = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            seen.append(n)
            return bytes(range(64))[:n]

    def urlopen(req, timeout):
        seen.append(req.get_header("Range"))
        return Resp()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert REAL_DEFAULT_HEAD("https://x/fw.bin", 16) == bytes(range(16))
    assert seen == ["bytes=0-15", 16]


# --- precedence, unknowns, budget ---------------------------------------------------------------------

def test_an_esp_target_wins_over_an_ambiguous_signal():
    res, _ = check(tree=["a.ino", "platformio.ini"], files={"platformio.ini": "[env:x]\nplatform = espressif32\n"})
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "platformio"


def test_needs_review_lists_every_ambiguous_signal():
    res, _ = check(tree=IDF_TREE + ["s/s.ino"], files={"CMakeLists.txt": IDF_CMAKE}, releases=release("fw.uf2"))
    assert res["verdict"] == dev.NEEDS_REVIEW
    assert [a["kind"] for a in res["ambiguous"]] == ["idf_project", "arduino_sketch", "release_bin"]


def test_needs_review_is_remembered_with_the_reject_ttl():
    res, _ = check(tree=["s.ino"], releases=[])
    assert dev.ttl_days(dev.reject_reason(res)) == memory.NO_BUILD_SIGNAL_DAYS


def test_unreadable_endpoints_are_unknown_never_a_rejection():
    """A 502 on the tree and the releases is not a fact about the repo: ok=None, retried soon."""
    res, _ = check(tree=["x.ino"], releases=[],
                   fail=("repos/o/r/git/trees/main?recursive=1", "repos/o/r/releases?per_page=10"))
    assert res["ok"] is None and res["verdict"] is None
    reason = dev.reject_reason(res)
    assert reason.startswith("device_evidence_unreadable:")
    assert dev.ttl_days(reason) == memory.UNRESOLVED_REJECT_DAYS


def test_an_unreadable_target_file_makes_an_ambiguous_repo_unknown_not_needs_review():
    """The file that could have confirmed the target failed to read: retry, don't send to review."""
    res, _ = check(tree=IDF_TREE + ["sdkconfig.defaults"], files={"CMakeLists.txt": IDF_CMAKE}, releases=[],
                   fail=("https://raw.githubusercontent.com/o/r/main/sdkconfig.defaults",))
    assert res["ok"] is None


def test_an_unreadable_bin_header_is_unknown():
    res, _ = check(tree=["README.md"], releases=release("fw.bin"), fail=(asset_url("fw.bin"),))
    assert res["ok"] is None


def test_not_device_firmware_uses_the_no_build_signal_ttl():
    assert dev.ttl_days("not_device_firmware: whatever") == memory.NO_BUILD_SIGNAL_DAYS


def test_call_cap_is_respected():
    many = [f"p{i}/platformio.ini" for i in range(10)]
    api, raw, head, log = fake_repo(tree=many, files={p: "[env:x]\nplatform = atmelavr\n" for p in many}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, head=head, ref="main", max_calls=4)
    assert res["calls"] <= 4 and len(log) <= 4


def test_budget_exceeded_propagates():
    def api(path):
        raise BudgetExceeded("tick budget")
    with pytest.raises(BudgetExceeded):
        dev.check("o/r", api=api, raw=lambda u: None, head=lambda u, n: None, ref="main")


def test_budget_exceeded_on_the_ranged_get_propagates():
    def head(url, n):
        raise BudgetExceeded("tick budget")
    api, raw, _h, _ = fake_repo(tree=["README.md"], releases=release("fw.bin"))
    with pytest.raises(BudgetExceeded):
        dev.check("o/r", api=api, raw=raw, head=head, ref="main")


def test_ref_defaults_to_head():
    api, raw, head, log = fake_repo(ref="HEAD", tree=["a.ino", "sketch.yaml"], files={"sketch.yaml": ESP_SKETCH_YAML})
    assert dev.check("o/r", api=api, raw=raw, head=head)["ok"] is True
    assert log[0] == ("api", "repos/o/r/git/trees/HEAD?recursive=1")


def test_platformio_pioarduino_platform_url_and_interpolation_count_as_espressif32():
    ini = "[common]\nplatform = https://github.com/pioarduino/platform-espressif32/releases/download/55.03.30/platform-espressif32.zip\n" \
          "[env:x]\nplatform = ${common.platform}\nboard = esp32dev\n"
    res, _ = check(tree=["firmware/platformio.ini"], files={"firmware/platformio.ini": ini})
    assert res["verdict"] == dev.ESP_TARGET and res["url"].startswith("https://github.com/o/r/blob/main/firmware/platformio.ini#L")


def test_platformio_for_a_non_espressif_platform_is_not_evidence():
    res, _ = check(tree=["platformio.ini", "src/main.cpp"], files={"platformio.ini": "[env:pico]\nplatform = raspberrypi\n"}, releases=[])
    assert res["verdict"] == dev.NOT_DEVICE_FIRMWARE


def test_platformio_platform_in_an_extra_config_file_counts():
    """Meshtastic-style: the root file only lists extra_configs; the platform lives in arch/*.ini."""
    root_ini = "[platformio]\nextra_configs =\n  arch/*/*.ini\n\n[env]\nframework = arduino\n"
    arch = "[esp32_base]\nplatform = platformio/espressif32@6.9.0\n"
    res, _ = check(tree=["platformio.ini", "arch/esp32/esp32.ini", "arch/nrf52/nrf52.ini"],
                   files={"platformio.ini": root_ini, "arch/esp32/esp32.ini": arch,
                          "arch/nrf52/nrf52.ini": "[nrf52_base]\nplatform = nordicnrf52\n"}, releases=[])
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/arch/esp32/esp32.ini#L2"


def test_platformio_platform_interpolated_from_another_option_counts():
    ini = "[common]\nesp32_platform = espressif32@6.4.0\n\n[env:x]\nplatform = ${common.esp32_platform}\nboard = esp32dev\n"
    res, _ = check(tree=["platformio.ini"], files={"platformio.ini": ini}, releases=[])
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/platformio.ini#L5"


def test_deferred_result_has_its_own_reason():
    reason = dev.reject_reason(dev.deferred("tick budget low"))
    assert reason.startswith("device_evidence_deferred:")


def test_review_note_carries_the_citation_and_every_reason():
    res, _ = check(tree=IDF_TREE + ["s/s.ino"], files={"CMakeLists.txt": IDF_CMAKE}, releases=[])
    note = dev.review_note(res)
    assert note["kind"] == "idf_project" and note["url"] == "https://github.com/o/r/blob/main/CMakeLists.txt#L2"
    assert "project.cmake" in note["why"] and "no ESP board named" in note["why"]


def test_default_head_treats_a_missing_asset_as_none_and_raises_on_an_outage(monkeypatch):
    import urllib.error
    import urllib.request

    def urlopen_with(code):
        def urlopen(req, timeout):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return urlopen
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_with(404))
    assert REAL_DEFAULT_HEAD("https://x/fw.bin", 16) is None
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_with(502))
    with pytest.raises(urllib.error.HTTPError):
        REAL_DEFAULT_HEAD("https://x/fw.bin", 16)


def test_a_targets_block_ends_at_the_next_top_level_key():
    """`targets:` then another key: a later list item belongs to that key, not to targets."""
    comp = "targets:\n  # supported\n  - linux\ndependencies:\n  - esp32s3\n"
    res, _ = check(tree=IDF_TREE + ["main/idf_component.yml"], releases=[],
                   files={"CMakeLists.txt": IDF_CMAKE, "main/idf_component.yml": comp})
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_a_vendored_library_example_is_not_the_repo_s_own_sketch():
    """lib/ (PlatformIO), libraries/ (Arduino) and other vendored trees carry other projects'
    sketches and compatibility claims: never evidence that THIS repo targets an ESP."""
    res, _ = check(tree=["platformio.ini", "src/main.cpp", "lib/SomeLib/examples/Demo/Demo.ino", "lib/SomeLib/library.properties"],
                   files={"platformio.ini": "[env:nrf]\nplatform = nordicnrf52\n",
                          "lib/SomeLib/library.properties": "architectures=esp32,nrf52\n"}, releases=[])
    assert res["verdict"] == dev.NOT_DEVICE_FIRMWARE


def test_a_vendored_board_file_does_not_name_the_repo_s_board():
    res, _ = check(tree=["app/app.ino", "libraries/Zap/library.properties", "libraries/Zap/sketch.yaml"],
                   files={"libraries/Zap/library.properties": "architectures=esp32\n", "libraries/Zap/sketch.yaml": ESP_SKETCH_YAML},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "arduino_sketch"


def test_a_root_arduino_library_with_architectures_esp32_still_counts():
    res, _ = check(tree=["library.properties", "examples/Basic/Basic.ino", "src/Zap.cpp"],
                   files={"library.properties": "name=Zap\narchitectures=esp32\n"})
    assert res["verdict"] == dev.ESP_TARGET


def test_an_exhausted_call_cap_with_an_ambiguous_signal_goes_to_review_not_retry():
    """Exhaustion is a property of the repo's shape (it recurs every retry), so an ambiguous
    signal found before the cap goes to the owner rather than looping as unknown."""
    many = [f"p{i}/CMakeLists.txt" for i in range(3)]
    api, raw, head, _ = fake_repo(tree=["CMakeLists.txt", "a.ino", "a/sketch.yaml"] + many,
                                  files={"CMakeLists.txt": IDF_CMAKE, "a/sketch.yaml": ESP_SKETCH_YAML}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, head=head, ref="main", max_calls=2)   # tree + root CMakeLists; sketch.yaml unread
    assert res["verdict"] == dev.NEEDS_REVIEW and any("call budget exhausted at 2" in n for n in res["notes"])


def test_an_exhausted_call_cap_with_nothing_found_is_unknown():
    many = [f"p{i}/platformio.ini" for i in range(10)]
    api, raw, head, _ = fake_repo(tree=many, files={p: "[env:x]\nplatform = atmelavr\n" for p in many}, releases=[])
    res = dev.check("o/r", api=api, raw=raw, head=head, ref="main", max_calls=4)
    assert res["ok"] is None and res["verdict"] is None
