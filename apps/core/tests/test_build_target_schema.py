"""The `build-target` fact (Jr redesign plan, step 2a, 2026-11-22).

Jr records only a configuration fact: "At commit S, PlatformIO V resolves env E of repo R to the board option B".
It is a recipe with status `build-target` carrying a `claim` block a trusted checker re-proves; it is never a
"runs on" claim, so it carries no flash action. A board links to such facts only through a cited
`platformio_definitions` entry (definition id + platform package + manifest digest).
"""
import copy

import pytest

from esp_atlas_core.frontmatter import parse_frontmatter
from esp_atlas_core.paths import REPO_ROOT
from esp_atlas_core.validate import validate_frontmatter

BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"
SHA = "971c066b37dbe3dbb9ac1096d9e72f32ab5b3452"
DIGEST = "a" * 64


def claim():
    return {
        "kind": "pio-env",
        "repo": {"slug": "PlummersSoftwareLLC/NightDriverStrip", "id": 289435913},
        "sha": SHA,
        "env": "heltecv3demo",
        "board_id": "heltec_wifi_kit_32_V3",
        "platformio_version": "6.2.0",
        "platform": {"spec": "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip",
                     "package_digest": DIGEST, "manifest_digest": "b" * 64},
        "files": [{"path": "platformio.ini", "blob": "c" * 40}],
        "sections": [{"name": "env:heltecv3demo", "file": "platformio.ini", "line": 842}],
    }


def build_target(**over):
    fm = {
        "id": "heltec-wifi-kit-32-v3__nightdriverstrip-bt",
        "type": "recipe",
        "board": "heltec-wifi-kit-32-v3",
        "firmware": "nightdriverstrip",
        "status": "build-target",
        "chip_family": "esp32-s3",
        "claim": claim(),
        "sources": [{"field": "claim", "url": f"https://github.com/PlummersSoftwareLLC/NightDriverStrip/blob/{SHA}/platformio.ini#L842",
                     "verified": "2026-11-22"}],
    }
    fm.update(over)
    return fm


def ok(fm, kind="recipe"):
    return validate_frontmatter(fm, kind, ids=None)


def test_a_build_target_fact_with_a_complete_claim_is_valid():
    assert ok(build_target()) == {"ok": True, "errors": []}


def test_build_target_without_a_claim_is_refused():
    fm = build_target()
    del fm["claim"]
    assert not ok(fm)["ok"]


def test_build_target_never_carries_a_flash_action():
    assert not ok(build_target(flash={"method": "release-bin"}))["ok"]


def test_a_claim_on_any_other_tier_is_refused():
    for status in ("known-good", "reported", "declared", "unverified", "broken"):
        assert not ok(build_target(status=status))["ok"], status


@pytest.mark.parametrize("path, bad", [
    (("sha",), "971c066b"),                                  # not a full 40-hex commit
    (("kind",), "readme"),                                   # only pio-env exists today
    (("repo", "id"), "289435913"),                           # numeric id, not a string
    (("platform", "package_digest"), "sha256:abc"),          # 64 lowercase hex only
    (("files",), []),                                        # at least one loaded file
    (("sections",), []),                                     # at least one contributing section
])
def test_a_malformed_claim_is_refused(path, bad):
    fm = build_target()
    node = fm["claim"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = bad
    assert not ok(fm)["ok"], path


def test_an_unknown_claim_field_is_refused():
    fm = build_target()
    fm["claim"]["runs_on"] = True
    assert not ok(fm)["ok"]


@pytest.fixture
def board_fm():
    fm, _ = parse_frontmatter(BOARD_PATH)
    return fm


def test_a_board_may_cite_its_platformio_definitions(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["platformio_definitions"] = [{"id": "esp32-c6-devkitc-1", "platform_package": "platformio/espressif32@6.9.0",
                                     "manifest_digest": DIGEST}]
    fm["sources"] = fm["sources"] + [{"field": "platformio_definitions",
                                      "url": "https://github.com/platformio/platform-espressif32/blob/v6.9.0/boards/esp32-c6-devkitc-1.json",
                                      "verified": "2026-11-22"}]
    assert ok(fm, "board") == {"ok": True, "errors": []}


def test_platformio_definitions_without_a_source_are_refused(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["platformio_definitions"] = [{"id": "esp32-c6-devkitc-1", "platform_package": "platformio/espressif32@6.9.0",
                                     "manifest_digest": DIGEST}]
    result = ok(fm, "board")
    assert not result["ok"] and any("platformio_definitions" in e for e in result["errors"])


def test_a_platformio_definition_needs_its_package_and_digest(board_fm):
    fm = copy.deepcopy(board_fm)
    fm["platformio_definitions"] = [{"id": "esp32-c6-devkitc-1"}]
    fm["sources"] = fm["sources"] + [{"field": "platformio_definitions", "url": "https://example.com/x.json",
                                      "verified": "2026-11-22"}]
    assert not ok(fm, "board")["ok"]
