"""THE ORACLE — jr/board_declared.py (SPEC-firmware-board-mapping.md §3.1, §3.3, §6).

Hermetic and deterministic: every fixture is a verbatim capture of the real upstream source
(fetched 2026-09-21 via `gh api`), and every network effect (`api`, `fetch`) is a fake — nothing
here touches the network. Two firmware, both P2 reference cases from the phase brief:

  - esp-claw (`espressif/esp-claw`): the manifest-tree extractor over its real
    `application/edge_agent/boards/<vendor>/<board>/` layout, captured as a git-tree blob-path
    listing (jr/fixtures/board_declared/esp-claw-tree.json — the 233 real board-manifest paths
    plus 15 real non-manifest paths from elsewhere in the repo, to prove the regex only matches
    under boards/).
  - evil-m5project (`7h30th3r0n3/Evil-M5Project`): the README-table extractor over its real
    README (jr/fixtures/board_declared/evil-m5project-README.md).

Every resolved/unresolved assertion below was checked against the REAL catalog
(`data/boards/*/*/board.md`) and the REAL fetched sources, not assumed — same discipline as
test_board_resolver.py's own oracle. One correction to the phase brief's own gloss, made by
running the extractor against the real README: the brief's reference-case description lists
"M5Stick v1.1/v2" as part of the "🧱 M5Stack Devices" table's yield, but the real README puts
those two rows in a SEPARATE, non-matching "🧪 In Beta" table sitting right after it (nested
inside the same outer "## Compatible Hardware" markdown section). readme_table_refs() treats
that inner heading as its own section boundary (SPEC §3.3: "the device cells, not surrounding
prose" — a non-matching heading must not inherit its non-matching neighbour's table just because
it is a markdown descendant), so M5Stick v1.1/v2 are correctly ABSENT from this extractor's
output. Asserting the brief's literal example here would be exactly the wrong-edge failure mode
SPEC §8 exists to catch.

Run: cd jr && python3 -m pytest test_board_declared.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import board_declared as bdec

FIX = Path(__file__).resolve().parent / "fixtures" / "board_declared"
ESP_CLAW_TREE = json.loads((FIX / "esp-claw-tree.json").read_text())
EVIL_M5PROJECT_README = (FIX / "evil-m5project-README.md").read_text()


class FakeApi:
    """api(path) backed by a dict; raises like a 404 for anything not registered."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        if path not in self.routes:
            raise RuntimeError(f"404: {path}")
        return self.routes[path]


def fake_readme(text: str):
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return text
    fetch.calls = calls
    return fetch


# ─────────────────────────── manifest tree (SPEC §3.1) ───────────────────────────

def test_manifest_tree_refs_recovers_esp_claws_39_boards():
    paths = [t["path"] for t in ESP_CLAW_TREE["tree"] if t["type"] == "blob"]
    found = bdec.manifest_tree_refs(paths)
    assert len(found["refs"]) == 39
    assert found["root"] == "application/edge_agent/boards"
    assert len(found["refs"]) == len(set(found["refs"]))          # deduped
    assert "m5stack_cores3" in found["refs"] and "esp32_p4_eye" in found["refs"]


def test_manifest_tree_refs_ignores_paths_outside_a_manifest_dir():
    non_manifest = [t["path"] for t in ESP_CLAW_TREE["tree"] if t["type"] == "blob"
                    and not t["path"].startswith("application/edge_agent/boards/")]
    assert non_manifest                                             # the fixture carries some
    assert bdec.manifest_tree_refs(non_manifest) == {"refs": [], "root": None}


def test_manifest_tree_refs_matches_variants_and_targets_dirs_too():
    found = bdec.manifest_tree_refs(["variants/acme/thing-one/main.c", "targets/acme/thing-two/main.c"])
    assert found["refs"] == ["thing-one", "thing-two"]


def test_extract_manifest_tree_calls_the_git_trees_api_and_cites_the_matched_dir():
    api = FakeApi({"repos/espressif/esp-claw/git/trees/master?recursive=1": ESP_CLAW_TREE})
    out = bdec.extract_manifest_tree("espressif/esp-claw", "master", api=api)
    assert api.calls == ["repos/espressif/esp-claw/git/trees/master?recursive=1"]
    assert len(out["refs"]) == 39
    assert out["source_type"] == "manifest_tree"
    assert out["source_url"] == "https://github.com/espressif/esp-claw/tree/master/application/edge_agent/boards"


def test_extract_manifest_tree_empty_when_repo_has_no_manifest_dir():
    api = FakeApi({"repos/o/r/git/trees/main?recursive=1": {"tree": [{"path": "src/main.c", "type": "blob"}]}})
    out = bdec.extract_manifest_tree("o/r", "main", api=api)
    assert out == {"refs": [], "source_url": None, "source_type": "manifest_tree"}


# --- esp-claw oracle: resolved boards + the P4/C5 boards resolve to nothing (never a SoC) --------

ESP_CLAW_RESOLVED = {
    "m5stack_cores3": "m5stack-cores3",
    "esp32_S3_DevKitC_1": "esp32-s3-devkitc-1",
    "dfrobot_firebeetle_2_ESP32_S3": "firebeetle-2-esp32-s3",
    "xiao_esp32s3_sense": "xiao-esp32s3-sense",
    "m5stack_sticks3": "m5stick-s3",
    "lilygo_t_display_s3": "lilygo-t-display-s3",
    "waveshare_ESP32_S3_RLCD_4_2": "waveshare-esp32-s3-rlcd-42",
}

ESP_CLAW_UNRESOLVED_P4_C5 = [
    "esp32_p4_eye", "movecall_moji2_esp32c5", "dfrobot_firebeetle_2_ESP32_C5_for_display",
]


def test_esp_claw_manifest_resolves_the_catalogued_boards_and_leaves_p4_c5_unresolved():
    paths = [t["path"] for t in ESP_CLAW_TREE["tree"] if t["type"] == "blob"]
    found = bdec.manifest_tree_refs(paths)
    import board_resolver as br
    result = br.resolve_boards(found["refs"])
    assert result["resolved"] == ESP_CLAW_RESOLVED
    for raw in ESP_CLAW_UNRESOLVED_P4_C5:
        assert raw in result["unresolved"]
    assert len(result["resolved"]) + len(result["unresolved"]) == 39


# ─────────────────────────── README device table (SPEC §3.3) ───────────────────────────

EVIL_M5PROJECT_REFS = [
    "M5Cardputer", "M5Stack Core2", "M5Stack Fire", "M5Stack Core1", "M5Stack AWS",
    "M5Stack CoreS3", "M5Stack CoreS3 SE", "M5AtomS3", "GPS Module", "LLM Module",
    "Evil with v1.3.0", "ESP32 devices", "External antenna",
]


def test_readme_table_refs_recovers_evil_m5project_device_names_cleaned():
    """The cell text carries decoration the resolver must never see: 'Better one : M5Cardputer'
    -> 'M5Cardputer', '↳ GPS Module' -> 'GPS Module', 'M5AtomS3 (GPS needed)' -> 'M5AtomS3'."""
    refs = bdec.readme_table_refs(EVIL_M5PROJECT_README)
    assert refs == EVIL_M5PROJECT_REFS


def test_readme_table_refs_never_pulls_in_a_non_matching_nested_heading():
    """'🧪 In Beta' (CYD2USB, CYD1USB, M5Stick v1.1, M5Stick v2) sits right after the matching
    '🧱 M5Stack Devices' table but under its OWN, non-matching heading — never captured."""
    refs = bdec.readme_table_refs(EVIL_M5PROJECT_README)
    for noise in ("CYD2USB", "CYD1USB", "M5Stick v1.1", "M5Stick v2"):
        assert noise not in refs


def test_readme_table_refs_never_pulls_in_the_feature_matrix_or_prose():
    """The 'Features may vary...' matrix and 'Required Extras'/'Hardware Requirements' prose
    paragraphs sit outside any Supported/Compatible/Devices/Hardware-matching table/list scope
    (or, for the one genuine bullet list SPEC §3.3 says to read, resolve to nothing — see the
    module docstring's correction note)."""
    refs = bdec.readme_table_refs(EVIL_M5PROJECT_README)
    for noise in ("Evil-Cardputer v1.5.4", "WiFi Network Scanning", "SD Card", "Feature"):
        assert noise not in refs


def test_readme_table_refs_no_heading_matches_returns_nothing():
    assert bdec.readme_table_refs("# Random\nsome text\n| a | b |\n|---|---|\n| x | y |\n") == []


def test_readme_table_refs_markdown_table_under_a_matching_heading():
    text = "## Supported Devices\n| Board | Note |\n|---|---|\n| Foo Board | ok |\n| Bar Board | ok |\n"
    assert bdec.readme_table_refs(text) == ["Foo Board", "Bar Board"]


def test_extract_readme_table_cites_the_repo_readme_and_the_source_type():
    fetch = fake_readme(EVIL_M5PROJECT_README)
    out = bdec.extract_readme_table("7h30th3r0n3/Evil-M5Project", fetch=fetch)
    assert fetch.calls == ["https://github.com/7h30th3r0n3/Evil-M5Project"]
    assert out["source_url"] == "https://github.com/7h30th3r0n3/Evil-M5Project#readme"
    assert out["source_type"] == "readme_table"
    assert out["refs"] == EVIL_M5PROJECT_REFS


# --- evil-m5project oracle: the catalogued devices resolve, the rest are surfaced unresolved ------

EVIL_M5PROJECT_RESOLVED = {
    "M5Cardputer": "m5cardputer",
    "M5Stack Core2": "m5stack-core2",
    "M5Stack CoreS3": "m5stack-cores3",
    "M5AtomS3": "m5atoms3",
}


def test_evil_m5project_readme_resolves_the_catalogued_devices():
    import board_resolver as br
    refs = bdec.readme_table_refs(EVIL_M5PROJECT_README)
    result = br.resolve_boards(refs)
    assert result["resolved"] == EVIL_M5PROJECT_RESOLVED
    assert len(result["resolved"]) + len(result["unresolved"]) == len(EVIL_M5PROJECT_REFS)
    for raw in ("M5Stack Fire", "M5Stack Core1", "M5Stack AWS", "M5Stack CoreS3 SE", "GPS Module", "LLM Module"):
        assert raw in result["unresolved"]


# ─────────────────────────── extract_declared_boards (the driver) ───────────────────────────

def test_extract_declared_boards_esp_claw_manifest_only():
    api = FakeApi({"repos/espressif/esp-claw/git/trees/master?recursive=1": ESP_CLAW_TREE})
    out = bdec.extract_declared_boards("espressif/esp-claw", "master", manifest_api=api,
                                       readme_fetch=fake_readme(""))
    assert set(out["resolved"]) == set(ESP_CLAW_RESOLVED.values())
    for board_id in ESP_CLAW_RESOLVED.values():
        entry = out["resolved"][board_id]
        assert entry["source_type"] == "manifest_tree"
        assert entry["source_url"] == "https://github.com/espressif/esp-claw/tree/master/application/edge_agent/boards"
    for raw in ESP_CLAW_UNRESOLVED_P4_C5:
        assert raw in out["unresolved"]
    assert out["socs"] == ["esp32-s3"]                    # every esp-claw resolved board is an S3


def test_extract_declared_boards_evil_m5project_readme_only():
    api = FakeApi({"repos/7h30th3r0n3/Evil-M5Project/git/trees/main?recursive=1": {"tree": []}})
    out = bdec.extract_declared_boards("7h30th3r0n3/Evil-M5Project", "main", manifest_api=api,
                                       readme_fetch=fake_readme(EVIL_M5PROJECT_README))
    assert set(out["resolved"]) == set(EVIL_M5PROJECT_RESOLVED.values())
    for board_id in EVIL_M5PROJECT_RESOLVED.values():
        assert out["resolved"][board_id]["source_type"] == "readme_table"
        assert out["resolved"][board_id]["source_url"] == "https://github.com/7h30th3r0n3/Evil-M5Project#readme"
    assert out["socs"] == ["esp32", "esp32-s3"]           # m5stack-core2 is classic esp32; the rest are S3


def test_extract_declared_boards_defaults_ref_to_the_default_branch():
    api = FakeApi({
        "repos/o/r": {"default_branch": "develop"},
        "repos/o/r/git/trees/develop?recursive=1": {"tree": []},
    })
    out = bdec.extract_declared_boards("o/r", manifest_api=api, readme_fetch=fake_readme(""))
    assert "repos/o/r/git/trees/develop?recursive=1" in api.calls
    assert out == {"resolved": {}, "unresolved": [], "socs": []}


def test_extract_declared_boards_never_drops_an_unresolved_ref():
    api = FakeApi({"repos/o/r/git/trees/main?recursive=1": {
        "tree": [{"path": "boards/acme/unknown-thing/main.c", "type": "blob"}]}})
    out = bdec.extract_declared_boards("o/r", "main", manifest_api=api, readme_fetch=fake_readme(""))
    assert out == {"resolved": {}, "unresolved": ["unknown-thing"], "socs": []}
