"""THE ORACLE — jr/board_declared.py manifest-tree scoping + per-ref provenance
(SPEC-firmware-board-mapping.md §3.1; plan 2026-11-05-nucleoos-correction.md spec A).

NucleoOS (indecenti/NucleoOs) vendored a study copy of esp-claw at `reference/esp-claw/...`;
its README says "These are not part of NucleoOS and are not built or shipped." The old regex
matched `boards/<vendor>/<board>/` at ANY depth, so that copy produced six false declared edges,
and every ref cited whichever root matched first. These oracles pin both fixes:

  - a manifest dir under a vendored / third-party / study tree yields no refs;
  - a nested FIRST-party root (esp-claw's own `application/edge_agent/boards`) is still kept;
  - every ref records the root it was found under, and each root gets its own source URL.

Hermetic: tree listings are inline blob-path lists, every `api`/`fetch` is a fake; nothing
touches the network or the repo's data dirs.

Run: cd jr && python3 -m pytest test_board_declared_provenance.py -v
"""
from __future__ import annotations

import pytest

import board_declared as bdec

NUCLEOOS_VENDORED = "reference/esp-claw/application/edge_agent/boards/m5stack/m5stack_cores3/board.yaml"
ESP_CLAW_FIRST_PARTY = "application/edge_agent/boards/m5stack/m5stack_cores3/board.yaml"

EXCLUDED_SEGMENTS = [
    "reference", "references", "third_party", "third-party", "thirdparty", "vendor", "vendored",
    "external", "extern", "deps", "managed_components",
]


def tree_api(owner_repo: str, ref: str, paths: list[str]):
    routes = {f"repos/{owner_repo}/git/trees/{ref}?recursive=1": {
        "tree": [{"path": p, "type": "blob"} for p in paths]}}

    def api(path: str):
        if path not in routes:
            raise RuntimeError(f"404: {path}")
        return routes[path]
    return api


def no_readme(url: str) -> str:
    return ""


# ─────────────────────────── vendored / study trees are skipped ───────────────────────────

def test_nucleoos_shaped_vendored_study_tree_yields_zero_refs():
    found = bdec.manifest_tree_refs([NUCLEOOS_VENDORED])
    assert found["refs"] == []
    assert found["root"] is None
    assert found["ref_roots"] == {}


def test_nucleoos_shaped_tree_extracts_and_resolves_nothing():
    api = tree_api("indecenti/NucleoOs", "main", [NUCLEOOS_VENDORED, "README.md", "src/main.c"])
    out = bdec.extract_manifest_tree("indecenti/NucleoOs", "main", api=api)
    assert out["refs"] == [] and out["source_url"] is None and out["source_urls"] == {}
    declared = bdec.extract_declared_boards("indecenti/NucleoOs", "main", manifest_api=api, readme_fetch=no_readme)
    assert declared == {"resolved": {}, "unresolved": [], "socs": []}


@pytest.mark.parametrize("segment", EXCLUDED_SEGMENTS)
def test_every_vendored_segment_before_the_manifest_dir_is_skipped(segment):
    assert bdec.manifest_tree_refs([f"{segment}/boards/acme/thing/main.c"])["refs"] == []
    assert bdec.manifest_tree_refs([f"a/{segment}/b/variants/acme/thing/main.c"])["refs"] == []


def test_vendored_segment_match_is_case_insensitive():
    assert bdec.manifest_tree_refs(["Third_Party/lib/targets/acme/thing/main.c"])["refs"] == []


def test_only_whole_segments_before_the_manifest_dir_count():
    # A lookalike segment name is not a vendored marker, and a marker word AFTER the manifest
    # dir (the vendor slot of boards/<vendor>/<board>/) is just a vendor name.
    found = bdec.manifest_tree_refs([
        "my_reference_app/boards/acme/thing-one/main.c",
        "boards/vendor/thing-two/main.c",
    ])
    assert found["refs"] == ["thing-one", "thing-two"]


# ─────────────────────────── first-party roots + per-ref provenance ───────────────────────────

def test_esp_claw_shaped_first_party_nested_root_keeps_the_ref_with_its_own_root_url():
    found = bdec.manifest_tree_refs([ESP_CLAW_FIRST_PARTY])
    assert found["refs"] == ["m5stack_cores3"]
    assert found["root"] == "application/edge_agent/boards"
    assert found["ref_roots"] == {"m5stack_cores3": "application/edge_agent/boards"}

    api = tree_api("espressif/esp-claw", "master", [ESP_CLAW_FIRST_PARTY])
    out = bdec.extract_manifest_tree("espressif/esp-claw", "master", api=api)
    url = "https://github.com/espressif/esp-claw/tree/master/application/edge_agent/boards"
    assert out["refs"] == ["m5stack_cores3"]
    assert out["source_url"] == url
    assert out["source_urls"] == {"application/edge_agent/boards": url}
    assert out["ref_roots"] == {"m5stack_cores3": "application/edge_agent/boards"}


TWO_ROOTS = [
    "boards/m5stack/m5stack_cores3/board.yaml",
    "firmware/variants/lilygo/lilygo_t_display_s3/pins.h",
]


def test_two_first_party_roots_each_ref_cites_its_own_root():
    found = bdec.manifest_tree_refs(TWO_ROOTS)
    assert found["refs"] == ["m5stack_cores3", "lilygo_t_display_s3"]
    assert found["roots"] == ["boards", "firmware/variants"]
    assert found["root"] == "boards"                                # first root, back-compat key
    assert found["ref_roots"] == {"m5stack_cores3": "boards", "lilygo_t_display_s3": "firmware/variants"}


def test_two_roots_extract_gives_a_source_url_per_root_and_the_driver_cites_each():
    api = tree_api("o/r", "main", TWO_ROOTS)
    out = bdec.extract_manifest_tree("o/r", "main", api=api)
    assert out["source_urls"] == {
        "boards": "https://github.com/o/r/tree/main/boards",
        "firmware/variants": "https://github.com/o/r/tree/main/firmware/variants",
    }
    assert out["source_url"] == "https://github.com/o/r/tree/main/boards"

    declared = bdec.extract_declared_boards("o/r", "main", manifest_api=api, readme_fetch=no_readme)
    assert declared["resolved"] == {
        "m5stack-cores3": {"source_url": "https://github.com/o/r/tree/main/boards",
                           "source_type": "manifest_tree"},
        "lilygo-t-display-s3": {"source_url": "https://github.com/o/r/tree/main/firmware/variants",
                                "source_type": "manifest_tree"},
    }


def test_mixed_tree_keeps_first_party_refs_and_drops_vendored_ones():
    paths = [
        NUCLEOOS_VENDORED,                                           # vendored first, so it can't win "root"
        "reference/esp-claw/application/edge_agent/boards/lilygo/lilygo_t_display_s3/board.yaml",
        "third_party/sdk/boards/espressif/esp32_S3_DevKitC_1/board.yaml",
        "boards/m5stack/m5stack_cardputer/board.yaml",
    ]
    found = bdec.manifest_tree_refs(paths)
    assert found["refs"] == ["m5stack_cardputer"]
    assert found["roots"] == ["boards"] and found["root"] == "boards"
    assert found["ref_roots"] == {"m5stack_cardputer": "boards"}

    api = tree_api("o/r", "main", paths)
    out = bdec.extract_manifest_tree("o/r", "main", api=api)
    assert out["source_urls"] == {"boards": "https://github.com/o/r/tree/main/boards"}
    declared = bdec.extract_declared_boards("o/r", "main", manifest_api=api, readme_fetch=no_readme)
    assert "m5stack-cores3" not in declared["resolved"]
    assert "lilygo-t-display-s3" not in declared["resolved"]
    assert "esp32-s3-devkitc-1" not in declared["resolved"]
