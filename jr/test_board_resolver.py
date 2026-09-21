"""THE ORACLE — jr/board_resolver.py (SPEC-firmware-board-mapping.md §6).

Hand-verified against the REAL catalog (`data/boards/*/*/board.md`), not assumed. Two
firmware sources, both directions of correctness:

  - esp-claw (`application/edge_agent/boards/<vendor>/<board>/` manifest tree): the
    clearly-catalogued dirs MUST resolve; the ESP32-P4/C5 dirs MUST NOT — pins
    under-extraction AND the SoC-rejection rule in one fixture set.
  - evil-m5project (README "M5Stack Devices" table): the catalogued devices MUST
    resolve; the rest are asserted resolved-or-unresolved by checking the real catalog,
    not by assuming the README's completeness — pins over-mapping (a device this repo's
    README lists but the catalog does not carry must never be forced onto a lookalike).

Two corrections to the phase brief's own examples, made by checking `data/boards/`
directly (the SPEC's central thesis is "prefer missing to wrong" — a false oracle
assertion would be exactly that):
  - `esp_box_3` has NO catalogued board (no `esp-box-3` id, no `esp-box*` dir at all) —
    asserted unresolved, not forced onto a nonexistent id.
  - `xiao_esp32s3_sense` exact-matches the catalog's OWN dedicated `xiao-esp32s3-sense`
    board (a distinct, real entry from `xiao-esp32s3`) — asserted against that, not the
    plain (non-Sense) sibling.

Run: cd jr && python3 -m pytest test_board_resolver.py -v
"""
from __future__ import annotations

import pytest

import board_resolver as br

# --- requirement 1: the naming-gulf normalization examples from the phase brief -----------------

@pytest.mark.parametrize("raw,expect", [
    ("m5stack_sticks3", "m5stick-s3"),
    ("esp32_S3_DevKitC_1", "esp32-s3-devkitc-1"),
    ("xiao_esp32s3_sense", "xiao-esp32s3-sense"),   # see module docstring: catalog has the dedicated Sense board
    ("m5stack_cores3", "m5stack-cores3"),
])
def test_resolve_normalizes_the_documented_naming_gulf(raw, expect):
    assert br.resolve(raw) == expect


def test_resolve_esp_box_3_is_unresolved_no_such_board_in_the_catalog():
    """The phase brief listed esp_box_3 -> esp-box-3 as 'clearly catalogued'; data/boards/
    has no esp-box-3 (or any esp-box) entry. Asserting the fabricated id here would be
    exactly the wrong-edge failure mode SPEC-firmware-board-mapping.md §8 exists to catch."""
    assert br.resolve("esp_box_3") is None


# --- requirement 2: the hard rule — a board reference never resolves to a SoC -------------------

@pytest.mark.parametrize("raw", [
    "esp32", "esp32-s3", "ESP32-S3", "esp32_s3", "esp32-p4", "esp32-c5", "esp32-c6",
    "esp32c2", "esp32-c3", "esp32-c61", "esp32-h2", "esp32-h4",
])
def test_a_bare_soc_family_name_never_resolves_to_a_board(raw):
    assert br.resolve(raw) is None


# --- ORACLE fixture 1: esp-claw manifest dir names (SPEC §6, source type = manifest tree) -------

ESP_CLAW_RESOLVED = {
    "m5stack_cores3": "m5stack-cores3",
    "esp32_S3_DevKitC_1": "esp32-s3-devkitc-1",
    "dfrobot_firebeetle_2_ESP32_S3": "firebeetle-2-esp32-s3",
    "xiao_esp32s3_sense": "xiao-esp32s3-sense",
}

ESP_CLAW_UNRESOLVED_SOC_BOARDS = [
    "esp32_p4_eye",
    "movecall_moji2_esp32c5",
    "dfrobot_firebeetle_2_ESP32_C5_for_display",
]


@pytest.mark.parametrize("raw,expect", list(ESP_CLAW_RESOLVED.items()))
def test_esp_claw_catalogued_boards_resolve(raw, expect):
    assert br.resolve(raw) == expect


@pytest.mark.parametrize("raw", ESP_CLAW_UNRESOLVED_SOC_BOARDS)
def test_esp_claw_p4_and_c5_board_dirs_never_collapse_onto_their_soc(raw):
    """These board dirs exist upstream but the catalog carries no board for them yet
    (only the esp32-p4 / esp32-c5 SoC records exist). The SoC-rejection rule means the
    resolver must refuse them outright, not collapse the board reference onto the chip."""
    got = br.resolve(raw)
    assert got is None
    assert got not in ("esp32-p4", "esp32-c5")


# --- ORACLE fixture 2: evil-m5project README device-table names (source type = README table) ----

EVIL_M5PROJECT_RESOLVED = {
    "M5Cardputer": "m5cardputer",
    "M5Stack Core2": "m5stack-core2",
    "M5AtomS3": "m5atoms3",
    "CoreS3": "m5stack-cores3",       # verified against data/boards/m5stack/m5stack-cores3 (name: CoreS3)
}

# Verified against the real catalog (data/boards/), not assumed: none of these README
# device names have a catalogued board. "Fire", "Core1" and the pre-Plus2 "StickC"
# revisions and the AWS variant are not in data/boards/ under any id/name/aka.
EVIL_M5PROJECT_UNRESOLVED = ["Fire", "Core1", "StickC v1.1", "StickC v2", "AWS"]


@pytest.mark.parametrize("raw,expect", list(EVIL_M5PROJECT_RESOLVED.items()))
def test_evil_m5project_catalogued_devices_resolve(raw, expect):
    assert br.resolve(raw) == expect


@pytest.mark.parametrize("raw", EVIL_M5PROJECT_UNRESOLVED)
def test_evil_m5project_uncatalogued_devices_are_unresolved(raw):
    assert br.resolve(raw) is None


# --- over-mapping guard: a generic/bare reference must never be forced onto a board --------------

@pytest.mark.parametrize("raw", ["ESP32-S3", "anyboard"])
def test_over_mapping_guard_generic_references_never_resolve(raw):
    assert br.resolve(raw) is None


# --- resolve_boards(): the batch API surfaces unresolved refs, never drops them ------------------

def test_resolve_boards_splits_resolved_and_unresolved_and_drops_nothing():
    raws = list(ESP_CLAW_RESOLVED) + ESP_CLAW_UNRESOLVED_SOC_BOARDS
    result = br.resolve_boards(raws)
    assert result["resolved"] == ESP_CLAW_RESOLVED
    assert sorted(result["unresolved"]) == sorted(ESP_CLAW_UNRESOLVED_SOC_BOARDS)
    assert set(result["resolved"]) | set(result["unresolved"]) == set(raws)


def test_resolve_boards_empty_input():
    assert br.resolve_boards([]) == {"resolved": {}, "unresolved": []}
