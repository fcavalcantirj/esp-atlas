"""device_evidence: target evidence must belong to the project being classified (independent review,
PR 1415). A host/server repo that only vendors an ESP example — under examples/, third_party/, a
git submodule, managed_components/ … — or keeps one in a subdir its own README/build files never
point to, is needs_review, never esp_target. Evidence counts from the repo root, or from the
project's declared build directory. Offline fakes only (test_device_evidence.fake_repo)."""
from __future__ import annotations

import device_evidence as dev
from test_device_evidence import IDF_CMAKE, ESP_SKETCH_YAML, check, fake_repo

ESP_INI = "[env:esp32dev]\nplatform = espressif32\nboard = esp32dev\nframework = arduino\n"
GO_SERVER = ["go.mod", "go.sum", "cmd/server/main.go", "internal/api/api.go", "README.md"]
PY_HOST = ["pyproject.toml", "src/hostpkg/__init__.py", "src/hostpkg/cli.py", "README.md"]
GO_README = "# server\n\nA Go server for Linux. Run `go run ./cmd/server`.\n"


def vendored_review(res, kind):
    assert res["ok"] is False and res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == kind
    assert dev.VENDORED_OR_EXAMPLE_ONLY in dev.reject_reason(res)
    assert dev.VENDORED_OR_EXAMPLE_ONLY in dev.review_note(res)["why"]


# --- the owner's fixtures --------------------------------------------------------------------------

def test_go_server_with_an_examples_platformio_espressif32_needs_review():
    res, _ = check(tree=GO_SERVER + ["examples/esp32/platformio.ini", "examples/esp32/src/main.cpp"],
                   files={"examples/esp32/platformio.ini": ESP_INI, "README.md": GO_README}, releases=[])
    vendored_review(res, "platformio")
    assert res["url"] == "https://github.com/o/r/blob/main/examples/esp32/platformio.ini#L2"


def test_python_host_with_a_third_party_idf_example_needs_review():
    ex = "third_party/esp-idf-example/"
    res, _ = check(tree=PY_HOST + [ex + "CMakeLists.txt", ex + "main/CMakeLists.txt", ex + "main/app.c", ex + "sdkconfig.defaults"],
                   files={ex + "CMakeLists.txt": IDF_CMAKE, ex + "sdkconfig.defaults": "CONFIG_IDF_TARGET=\"esp32s3\"\n"},
                   releases=[])
    vendored_review(res, "idf_project")


def test_a_platformio_ini_inside_a_gitmodules_submodule_needs_review():
    gitmodules = '[submodule "esp-fw"]\n\tpath = ext/esp-fw\n\turl = https://github.com/x/esp-fw\n'
    res, _ = check(tree=GO_SERVER + [".gitmodules", "ext/esp-fw/platformio.ini"],
                   files={".gitmodules": gitmodules, "ext/esp-fw/platformio.ini": ESP_INI}, releases=[])
    vendored_review(res, "platformio")


def test_a_submodule_gitlink_in_the_tree_is_vendored_even_without_gitmodules():
    api, raw, fetch, _ = fake_repo(tree=["README.md", "fw/platformio.ini"], files={"fw/platformio.ini": ESP_INI}, releases=[])

    def with_gitlink(path):
        doc = api(path)
        if path.startswith("repos/o/r/git/trees/"):
            doc["tree"].append({"path": "fw", "type": "commit"})
        return doc
    vendored_review(dev.check("o/r", api=with_gitlink, raw=raw, fetch=fetch, ref="main"), "platformio")


def test_a_root_platformio_espressif32_is_still_esp_target_beside_vendored_examples():
    res, _ = check(tree=GO_SERVER + ["platformio.ini", "examples/other/platformio.ini"],
                   files={"platformio.ini": ESP_INI, "examples/other/platformio.ini": ESP_INI})
    assert res["ok"] is True and res["verdict"] == dev.ESP_TARGET
    assert res["url"] == "https://github.com/o/r/blob/main/platformio.ini#L2"


def test_a_firmware_dir_the_readme_points_to_is_esp_target():
    readme = "# thing\n\nServer in Go. Device firmware: `cd firmware && pio run -t upload`.\n"
    res, _ = check(tree=GO_SERVER + ["firmware/platformio.ini", "firmware/src/main.cpp"],
                   files={"README.md": readme, "firmware/platformio.ini": ESP_INI})
    assert res["ok"] is True and res["verdict"] == dev.ESP_TARGET and res["kind"] == "platformio"
    assert res["url"] == "https://github.com/o/r/blob/main/firmware/platformio.ini#L2"


def test_a_firmware_dir_a_root_makefile_points_to_is_esp_target():
    makefile = "flash:\n\tpio run -d firmware -t upload\n"
    res, _ = check(tree=GO_SERVER + ["Makefile", "firmware/platformio.ini"],
                   files={"README.md": GO_README, "Makefile": makefile, "firmware/platformio.ini": ESP_INI})
    assert res["verdict"] == dev.ESP_TARGET


managed = "managed_components/espressif__led_strip/"


def test_managed_components_only_needs_review():
    res, _ = check(tree=["README.md", "main.go", "go.mod", managed + "idf_component.yml", managed + "src/led_strip.c",
                         managed + "examples/rmt/CMakeLists.txt", managed + "examples/rmt/sdkconfig.defaults"],
                   files={managed + "idf_component.yml": "targets:\n  - esp32s3\n",
                          managed + "examples/rmt/CMakeLists.txt": IDF_CMAKE,
                          managed + "examples/rmt/sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32s3\n"}, releases=[])
    vendored_review(res, "idf_project")


def test_a_managed_components_manifest_alone_needs_review():
    res, _ = check(tree=["README.md", managed + "idf_component.yml", managed + "src/led_strip.c"],
                   files={managed + "idf_component.yml": "targets:\n  - esp32s3\n"}, releases=[])
    vendored_review(res, "idf_component")


# --- host repo, ESP evidence in a subdir that is not the declared project ---------------------------

def test_a_host_repo_with_an_undeclared_esp_subdir_needs_review():
    res, _ = check(tree=GO_SERVER + ["device/platformio.ini"], files={"README.md": GO_README, "device/platformio.ini": ESP_INI},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "platformio"
    assert dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res)


def test_a_host_repo_firmware_dir_without_a_pointer_needs_review():
    res, _ = check(tree=PY_HOST + ["firmware/CMakeLists.txt", "firmware/sdkconfig.defaults"],
                   files={"README.md": "# host tool\n", "firmware/CMakeLists.txt": IDF_CMAKE,
                          "firmware/sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res)


def test_a_readme_pointer_into_an_examples_dir_does_not_make_it_the_project():
    readme = "Try the device demo: `cd examples/esp32 && pio run`.\n"
    res, _ = check(tree=GO_SERVER + ["examples/esp32/platformio.ini"],
                   files={"README.md": readme, "examples/esp32/platformio.ini": ESP_INI}, releases=[])
    vendored_review(res, "platformio")


def test_a_word_firmware_in_the_readme_is_not_a_pointer():
    readme = "This server talks to stock firmware over WebSocket.\n"
    res, _ = check(tree=GO_SERVER + ["firmware/platformio.ini"], files={"README.md": readme, "firmware/platformio.ini": ESP_INI},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_a_vendored_non_esp_platformio_is_not_evidence_at_all():
    res, _ = check(tree=GO_SERVER + ["examples/pico/platformio.ini"],
                   files={"examples/pico/platformio.ini": "[env:pico]\nplatform = raspberrypi\n"}, releases=[])
    assert res["verdict"] == dev.NOT_DEVICE_FIRMWARE


# --- the IDF target must be the project's own --------------------------------------------------------

def test_a_root_idf_project_does_not_borrow_a_target_from_an_example():
    res, _ = check(tree=["CMakeLists.txt", "main/CMakeLists.txt", "main/app.c", "examples/demo/sdkconfig.defaults"],
                   files={"CMakeLists.txt": IDF_CMAKE, "examples/demo/sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32\n"},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "idf_project"
    assert "no ESP target stated" in dev.reject_reason(res)


def test_an_sdkconfig_outside_the_project_dir_is_another_project_s():
    """ESP-IDF reads sdkconfig.defaults and dependencies.lock from the project directory only; an
    idf_component.yml may sit in any of the project's own component dirs (main/, components/x/)."""
    res, _ = check(tree=["CMakeLists.txt", "main/app.c", "other/sdkconfig.defaults"],
                   files={"CMakeLists.txt": IDF_CMAKE, "other/sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and "no ESP target stated" in dev.reject_reason(res)


def test_a_declared_idf_firmware_dir_with_its_own_target_is_esp_target():
    readme = "Build the device with `idf.py -C firmware build`.\n"
    res, _ = check(tree=GO_SERVER + ["firmware/CMakeLists.txt", "firmware/main/app.c", "firmware/sdkconfig.defaults"],
                   files={"README.md": readme, "firmware/CMakeLists.txt": IDF_CMAKE,
                          "firmware/sdkconfig.defaults": "CONFIG_IDF_TARGET=esp32c3\n"})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/firmware/sdkconfig.defaults#L1"


# --- arduino: the board and the sketch must be the repo's own -----------------------------------------

def test_an_example_sketch_with_an_esp_sketch_yaml_in_a_go_repo_needs_review():
    res, _ = check(tree=GO_SERVER + ["examples/esp32/esp32.ino", "examples/esp32/sketch.yaml"],
                   files={"examples/esp32/sketch.yaml": ESP_SKETCH_YAML}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_a_root_workflow_compiling_only_an_example_sketch_needs_review():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/esp32\n"
    res, _ = check(tree=GO_SERVER + ["examples/esp32/esp32.ino", ".github/workflows/esp.yml"],
                   files={".github/workflows/esp.yml": wf}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_a_root_workflow_counts_for_a_declared_sketch_in_a_host_repo():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 firmware\n"
    res, _ = check(tree=GO_SERVER + ["firmware/firmware.ino", ".github/workflows/esp.yml"],
                   files={".github/workflows/esp.yml": wf, "README.md": "Flash `firmware/firmware.ino`.\n"})
    assert res["verdict"] == dev.ESP_TARGET and res["kind"] == "arduino_sketch"


# --- checker pass: pointers, unlisted vendored names, truncation, sketches a board file is for ------

def test_a_dir_name_in_prose_is_not_a_pointer():
    readme = "A Go server that works with any ESP32 device/firmware combination.\n"
    res, _ = check(tree=GO_SERVER + ["device/platformio.ini"], files={"README.md": readme, "device/platformio.ini": ESP_INI},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res)


def test_a_docker_detach_flag_is_not_a_pointer():
    res, _ = check(tree=GO_SERVER + ["Makefile", "device/platformio.ini"],
                   files={"README.md": GO_README, "Makefile": "up:\n\tdocker compose up -d device\n", "device/platformio.ini": ESP_INI},
                   releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_a_readme_path_to_the_dir_s_build_file_is_a_pointer():
    readme = "Flash the board: open `device/platformio.ini` in PlatformIO.\n"
    res, _ = check(tree=GO_SERVER + ["device/platformio.ini"], files={"README.md": readme, "device/platformio.ini": ESP_INI})
    assert res["verdict"] == dev.ESP_TARGET


def test_unlisted_vendored_spellings_and_example_named_dirs_do_not_count():
    for d in ("third-party/esp32-demo/", "thirdparty/x/", "3rdparty/x/", "deps/x/", "extern/x/", "esp32-example/", "esp32_demo/"):
        res, _ = check(tree=["src/main.c", d + "platformio.ini"], files={d + "platformio.ini": ESP_INI}, releases=[])
        assert res["verdict"] == dev.NEEDS_REVIEW and dev.VENDORED_OR_EXAMPLE_ONLY in dev.reject_reason(res), d


def test_a_plain_cmake_root_project_is_a_root_project_too():
    """A root CMakeLists.txt / Makefile / meson.build / requirements.txt is a project of its own: an
    ESP signal in a subdir must be pointed to."""
    for root in ("CMakeLists.txt", "Makefile", "meson.build", "requirements.txt"):
        res, _ = check(tree=[root, "src/main.cpp", "device/platformio.ini"],
                       files={root: "project(server CXX)\n", "device/platformio.ini": ESP_INI}, releases=[])
        assert res["verdict"] == dev.NEEDS_REVIEW and dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res), root


def test_a_truncated_listing_cannot_prove_there_is_no_host_manifest():
    api, raw, fetch, _ = fake_repo(tree=["esp32/platformio.ini"], files={"esp32/platformio.ini": ESP_INI}, releases=[])

    def truncated(path):
        doc = api(path)
        if path.startswith("repos/o/r/git/trees/"):
            doc["truncated"] = True
        return doc
    res = dev.check("o/r", api=truncated, raw=raw, fetch=fetch, ref="main")
    assert res["verdict"] == dev.NEEDS_REVIEW and dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res)


def test_an_arduino_library_s_examples_are_its_own_for_its_ci():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/Basic\n"
    res, _ = check(tree=["library.properties", "src/Zap.cpp", "examples/Basic/Basic.ino", ".github/workflows/ci.yml"],
                   files={"library.properties": "name=Zap\narchitectures=*\n", ".github/workflows/ci.yml": wf})
    assert res["verdict"] == dev.ESP_TARGET and res["url"] == "https://github.com/o/r/blob/main/.github/workflows/ci.yml#L4"


def test_an_arduino_library_example_sketch_yaml_is_its_own():
    res, _ = check(tree=["library.properties", "src/Zap.cpp", "examples/Basic/Basic.ino", "examples/Basic/sketch.yaml"],
                   files={"library.properties": "architectures=*\n", "examples/Basic/sketch.yaml": ESP_SKETCH_YAML})
    assert res["verdict"] == dev.ESP_TARGET


def test_a_workflow_esp_compile_counts_for_the_sketch_it_builds_only():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/esp32\n"
    res, _ = check(tree=["Blink/Blink.ino", "examples/esp32/esp32.ino", ".github/workflows/ci.yml"],
                   files={".github/workflows/ci.yml": wf}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_a_sketch_yaml_is_its_own_folder_s_sketch():
    res, _ = check(tree=["Blink/Blink.ino", "Other/sketch.yaml"], files={"Other/sketch.yaml": ESP_SKETCH_YAML}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW


def test_an_undeclared_idf_component_says_so():
    res, _ = check(tree=GO_SERVER + ["device/main/idf_component.yml"],
                   files={"README.md": GO_README, "device/main/idf_component.yml": "targets:\n  - esp32\n"}, releases=[])
    assert res["verdict"] == dev.NEEDS_REVIEW and res["kind"] == "idf_component"
    assert dev.UNDECLARED_PROJECT_DIR in dev.reject_reason(res)


# --- checker pass 2 -----------------------------------------------------------------------------------

def test_a_markdown_link_to_a_file_in_the_dir_is_not_a_pointer():
    for readme in ("![the stock device](device/photo.jpg)\n", "see [the wire protocol](device/PROTOCOL.md)\n"):
        res, _ = check(tree=GO_SERVER + ["device/platformio.ini"], files={"README.md": readme, "device/platformio.ini": ESP_INI},
                       releases=[])
        assert res["verdict"] == dev.NEEDS_REVIEW, readme


def test_a_markdown_link_to_the_dir_itself_is_a_pointer():
    res, _ = check(tree=GO_SERVER + ["device/platformio.ini"],
                   files={"README.md": "Firmware: [device](./device/)\n", "device/platformio.ini": ESP_INI})
    assert res["verdict"] == dev.ESP_TARGET


def test_a_multi_step_workflow_s_esp_compile_counts_only_for_its_own_line_s_sketch():
    wf = ("name: Blink CI\njobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn arduino:avr:uno Blink\n"
          "      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/esp32\n")
    res, _ = check(tree=["Blink/Blink.ino", "examples/esp32/esp32.ino", ".github/workflows/ci.yml"],
                   files={".github/workflows/ci.yml": wf}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_a_root_sketch_is_not_what_a_workflow_compiling_an_example_builds():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/esp32\n"
    res, _ = check(tree=["a.ino", "examples/esp32/esp32.ino", ".github/workflows/ci.yml"],
                   files={".github/workflows/ci.yml": wf}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_an_arduino_library_example_named_like_an_example_is_still_its_own():
    res, _ = check(tree=["library.properties", "src/Zap.cpp", "examples/ESP32_Example/ESP32_Example.ino"],
                   files={"library.properties": "architectures=esp32\n"})
    assert res["verdict"] == dev.ESP_TARGET


def test_the_declared_dir_keeps_its_slot_under_the_build_file_cap():
    nrf = "[env:nrf]\nplatform = nordicnrf52\n"
    res, _ = check(tree=PY_HOST + ["alpha/platformio.ini", "beta/platformio.ini", "bridge/platformio.ini", "firmware/platformio.ini"],
                   files={"README.md": "cd firmware && pio run\n", "alpha/platformio.ini": nrf, "beta/platformio.ini": nrf,
                          "bridge/platformio.ini": nrf, "firmware/platformio.ini": ESP_INI})
    assert res["verdict"] == dev.ESP_TARGET


def test_a_library_example_sketch_yaml_keeps_its_slot_under_the_board_file_cap():
    plain = "jobs:\n  b:\n    steps:\n      - run: echo lint\n"
    wfs = [f".github/workflows/w{i}.yml" for i in range(3)]
    res, _ = check(tree=["library.properties", "examples/Basic/Basic.ino", "examples/Basic/sketch.yaml"] + wfs,
                   files={"library.properties": "architectures=*\n", "examples/Basic/sketch.yaml": ESP_SKETCH_YAML,
                          **{w: plain for w in wfs}})
    assert res["verdict"] == dev.ESP_TARGET


# --- checker pass 3 -----------------------------------------------------------------------------------

def test_an_fqbn_token_is_not_a_sketch_folder_name():
    wf = "jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 examples/demo\n"
    res, _ = check(tree=["esp32/esp32.ino", "examples/demo/demo.ino", ".github/workflows/ci.yml"],
                   files={".github/workflows/ci.yml": wf}, releases=[])
    vendored_review(res, "arduino_sketch")


def test_compile_sketches_sketch_paths_are_built_for_the_workflow_s_esp_fqbn():
    wf = ("jobs:\n  b:\n    steps:\n      - uses: arduino/compile-sketches@v1\n        with:\n"
          "          fqbn: esp32:esp32:esp32s3\n          sketch-paths: |\n            - firmware\n")
    res, _ = check(tree=["firmware/firmware.ino", "examples/demo/demo.ino", ".github/workflows/ci.yml"],
                   files={".github/workflows/ci.yml": wf})
    assert res["verdict"] == dev.ESP_TARGET and "firmware/firmware.ino" in " ".join(res["notes"])


def test_a_root_sketch_compiled_by_file_name_or_dot_is_named():
    for target in ("Foo.ino", "."):
        wf = f"jobs:\n  b:\n    steps:\n      - run: arduino-cli compile --fqbn esp32:esp32:esp32 {target}\n"
        res, _ = check(tree=["Foo.ino", "examples/demo/demo.ino", ".github/workflows/ci.yml"],
                       files={".github/workflows/ci.yml": wf})
        assert res["verdict"] == dev.ESP_TARGET, target
